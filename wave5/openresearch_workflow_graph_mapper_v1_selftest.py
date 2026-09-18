#!/usr/bin/env python3
from __future__ import annotations

import copy
import json

from openresearch_workflow_graph_mapper_v1 import MapperError, map_to_workflow_graph


def projection():
    experiments = [
        {
            "experiment_id": "base",
            "parent_experiment_id": None,
            "title": "Baseline",
            "branch": "orx/base",
            "commit_sha": "1" * 40,
            "source_status": "answered",
            "authority": "NONE",
            "evidence_refs": ["orx-run:base:log"],
            "run": {
                "run_id": "run-base",
                "source_status": "done",
                "result_claim": "synthetic_score=0.70",
                "claim_verification": "UNVERIFIED_EXTERNAL",
                "evidence_refs": ["orx-run:base:log"],
            },
        },
        {
            "experiment_id": "child-a",
            "parent_experiment_id": "base",
            "title": "Variant A",
            "branch": "orx/child-a",
            "commit_sha": "2" * 40,
            "source_status": "answered",
            "authority": "NONE",
            "evidence_refs": ["orx-run:a:log"],
            "run": {
                "run_id": "run-a",
                "source_status": "done",
                "result_claim": "synthetic_score=0.80",
                "claim_verification": "UNVERIFIED_EXTERNAL",
                "evidence_refs": ["orx-run:a:log"],
            },
        },
        {
            "experiment_id": "child-b",
            "parent_experiment_id": "base",
            "title": "Variant B",
            "branch": "orx/child-b",
            "commit_sha": "3" * 40,
            "source_status": "provisional",
            "authority": "NONE",
            "evidence_refs": [],
            "run": {
                "run_id": "run-b",
                "source_status": "running",
                "result_claim": None,
                "claim_verification": "NO_RESULT_CLAIM",
                "evidence_refs": [],
            },
        },
        {
            "experiment_id": "grandchild",
            "parent_experiment_id": "child-a",
            "title": "Follow-up",
            "branch": "orx/grandchild",
            "commit_sha": "4" * 40,
            "source_status": "unknown",
            "authority": "NONE",
            "evidence_refs": [],
            "run": None,
        },
    ]
    return {
        "schema": "panam.openresearch.research-projection.v1",
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
            "reason": "external metadata only",
        },
        "upstream": {
            "repository": "alphaXiv/OpenResearch",
            "commit_sha": "69768ff1b0537a4656e69f550fc444ac35b945d2",
            "version": "0.2.5",
        },
        "project": {"project_id": "proj-demo", "name": "Synthetic project"},
        "source_manifest_sha256": "a" * 64,
        "experiments": experiments,
        "edges": [
            {"edge_id": "base->child-a", "from": "base", "to": "child-a", "edge_type": "parent_child"},
            {"edge_id": "base->child-b", "from": "base", "to": "child-b", "edge_type": "parent_child"},
            {"edge_id": "child-a->grandchild", "from": "child-a", "to": "grandchild", "edge_type": "parent_child"},
        ],
        "warnings": [
            "RESULT_CLAIM_REQUIRES_WORK_VERIFICATION:base:run-base",
            "RESULT_CLAIM_REQUIRES_WORK_VERIFICATION:child-a:run-a",
        ],
    }


def expect_error(value, needle):
    try:
        map_to_workflow_graph(value)
    except MapperError as exc:
        if needle not in str(exc):
            raise AssertionError(f"expected {needle!r}, got {exc!r}") from exc
        return
    raise AssertionError(f"expected MapperError containing {needle!r}")


def node_by_title(graph, title):
    return next(node for node in graph["nodes"] if node["title"] == title)


def main():
    passed = 0

    source = projection()
    graph = map_to_workflow_graph(source)
    assert graph["schema"] == "panam.workflow.graph.v1"
    assert graph["source_of_truth"] is False
    assert graph["projection_only"] is True
    assert graph["job_binding"]["bound"] is False
    assert graph["job_binding"]["authoritative_job_id"] is None
    assert graph["runtime_observation"]["authoritative_runtime_bound"] is False
    assert graph["runtime_observation"]["active_nodes"] == []
    assert all(node["authority"] == "NONE" for node in graph["nodes"])
    passed += 1

    permuted = projection()
    permuted["experiments"] = list(reversed(permuted["experiments"]))
    permuted["edges"] = list(reversed(permuted["edges"]))
    assert map_to_workflow_graph(permuted) == graph
    passed += 1

    rendered = json.dumps(graph, sort_keys=True)
    assert "synthetic_score=0.70" not in rendered
    assert "synthetic_score=0.80" not in rendered
    assert "openresearch-claim-verification:UNVERIFIED_EXTERNAL" in rendered
    passed += 1

    provisional = node_by_title(graph, "Variant B")
    assert provisional["state"] == "planned"
    assert all(node["state"] != "running" for node in graph["nodes"])
    assert graph["runtime_observation"]["active_nodes"] == []
    passed += 1

    base_node = node_by_title(graph, "Baseline")
    follow_node = node_by_title(graph, "Follow-up")
    base_edges = [e for e in graph["edges"] if e["from"] == base_node["node_id"]]
    assert len(base_edges) == 2
    assert all(e["edge_type"] == "fanout" for e in base_edges)
    follow_edge = next(e for e in graph["edges"] if e["to"] == follow_node["node_id"])
    assert follow_edge["edge_type"] == "sequential"
    passed += 1

    bad = projection()
    bad["authority"]["source_of_truth"] = True
    expect_error(bad, "input_authority_not_fail_closed")
    passed += 1

    bad = projection()
    bad["job_binding"]["bound"] = True
    bad["job_binding"]["authoritative_job_id"] = "job-123"
    expect_error(bad, "input_authoritative_job_binding_forbidden")
    passed += 1

    bad = projection()
    bad["edges"] = bad["edges"][:-1]
    expect_error(bad, "input_edges_do_not_match_parent_links")
    passed += 1

    bad = projection()
    bad["experiments"].append(copy.deepcopy(bad["experiments"][0]))
    expect_error(bad, "duplicate_experiment_id")
    passed += 1

    bad = projection()
    bad["experiments"][0]["title"] = "x" * 201
    expect_error(bad, "text_too_long")
    passed += 1

    print(f"PANAM_OPENRESEARCH_WORKFLOW_GRAPH_MAPPER_V1={passed}/10_PASS")
    print("GRAPH_SOURCE_OF_TRUTH=NO")
    print("AUTHORITATIVE_RUNTIME_BOUND=NO")
    print("ACTIVE_NODES_INFERRED=NO")
    print("RESULT_CLAIM_TEXT_COPIED=NO")


if __name__ == "__main__":
    main()

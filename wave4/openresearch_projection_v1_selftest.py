#!/usr/bin/env python3
from __future__ import annotations

import copy
import json

from openresearch_projection_v1 import (
    OUTPUT_SCHEMA,
    ProjectionError,
    build_projection,
)

UPSTREAM_SHA = "69768ff1b0537a4656e69f550fc444ac35b945d2"


def fixture():
    return {
        "schema": "openresearch.panam-export.v1",
        "upstream": {
            "repository": "alphaXiv/OpenResearch",
            "commit_sha": UPSTREAM_SHA,
            "version": "0.2.5",
        },
        "project": {
            "project_id": "proj-demo",
            "name": "Synthetic retrieval benchmark",
        },
        "experiments": [
            {
                "experiment_id": "exp-child",
                "parent_experiment_id": "exp-base",
                "title": "Hybrid retrieval",
                "branch": "orx/hybrid-retrieval",
                "commit_sha": "2" * 40,
                "source_status": "answered",
                "run": {
                    "run_id": "run-child",
                    "status": "done",
                    "result_claim": "synthetic_score=0.82",
                    "evidence_refs": [
                        "orx-run:run-child:log",
                        "orx-run:run-child:commit",
                    ],
                },
            },
            {
                "experiment_id": "exp-base",
                "parent_experiment_id": None,
                "title": "Baseline",
                "branch": "orx/baseline",
                "commit_sha": "1" * 40,
                "source_status": "answered",
                "run": {
                    "run_id": "run-base",
                    "status": "done",
                    "result_claim": "synthetic_score=0.71",
                    "evidence_refs": ["orx-run:run-base:log"],
                },
            },
        ],
    }


def expect_error(source, needle):
    try:
        build_projection(source)
    except ProjectionError as exc:
        if needle not in str(exc):
            raise AssertionError(f"expected {needle!r}, got {exc!r}") from exc
        return
    raise AssertionError(f"expected ProjectionError containing {needle!r}")


def main():
    passed = 0

    out = build_projection(fixture())
    assert out["schema"] == OUTPUT_SCHEMA
    assert out["authority"] == {
        "source_of_truth": False,
        "projection_only": True,
        "execution_authorized": False,
        "owner_approval_satisfied": False,
        "private_data_eligible": False,
    }
    assert out["job_binding"]["bound"] is False
    assert out["job_binding"]["authoritative_job_id"] is None
    assert [x["experiment_id"] for x in out["experiments"]] == [
        "exp-base",
        "exp-child",
    ]
    assert out["edges"] == [
        {
            "edge_id": "exp-base->exp-child",
            "from": "exp-base",
            "to": "exp-child",
            "edge_type": "parent_child",
        }
    ]
    passed += 1

    permuted = fixture()
    permuted["experiments"] = list(reversed(permuted["experiments"]))
    assert build_projection(permuted) == out
    passed += 1

    child = next(x for x in out["experiments"] if x["experiment_id"] == "exp-child")
    assert child["run"]["claim_verification"] == "UNVERIFIED_EXTERNAL"
    assert any(
        item.startswith("RESULT_CLAIM_REQUIRES_WORK_VERIFICATION:exp-child:")
        for item in out["warnings"]
    )
    passed += 1

    bad = fixture()
    bad["unexpected"] = True
    expect_error(bad, "unknown_keys:$")
    passed += 1

    bad = fixture()
    bad["upstream"]["api_token"] = "not-a-real-value"
    expect_error(bad, "secret_like_key")
    passed += 1

    bad = fixture()
    bad["experiments"][0]["parent_experiment_id"] = "missing"
    expect_error(bad, "missing_parent")
    passed += 1

    bad = fixture()
    bad["experiments"][1]["parent_experiment_id"] = "exp-child"
    expect_error(bad, "parent_cycle")
    passed += 1

    bad = fixture()
    bad["experiments"][0]["source_status"] = "answered"
    bad["experiments"][0]["run"]["status"] = "running"
    expect_error(bad, "answered_without_terminal_run")
    passed += 1

    bad = fixture()
    bad["upstream"]["commit_sha"] = "f" * 40
    expect_error(bad, "unsupported_upstream_sha")
    passed += 1

    bad = fixture()
    duplicate = copy.deepcopy(bad["experiments"][0])
    bad["experiments"].append(duplicate)
    bad["upstream"]["commit_sha"] = UPSTREAM_SHA
    expect_error(bad, "duplicate_experiment_id")
    passed += 1

    bad = fixture()
    bad["experiments"][0]["run"]["evidence_refs"] = []
    expect_error(bad, "result_claim_without_evidence_ref")
    passed += 1

    print(f"PANAM_OPENRESEARCH_DEVELOPER_ADAPTER_V1={passed}/11_PASS")
    print("SOURCE_OF_TRUTH=NO")
    print("EXECUTION_AUTHORITY=NO")
    print("AUTHORITATIVE_JOB_BINDING=NO")


if __name__ == "__main__":
    main()

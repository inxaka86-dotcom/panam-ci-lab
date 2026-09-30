#!/usr/bin/env python3
"""Scale replication of the FlyCore delayed-order signal at 192 real neurons."""

from __future__ import annotations

import argparse
import json
import math

import numpy as np

import run_real_subgraph_canary as base
import run_delay_sweep_robustness as sweep

NODE_COUNT = 192
DELAY = 16
SEEDS = (5, 11, 17, 29, 47)


def sign_test_two_sided(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return 1.0
    tail = min(wins, losses)
    return min(
        1.0,
        2.0 * sum(math.comb(n, k) for k in range(tail + 1)) / (2 ** n),
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--graph", required=True, type=base.Path)
    p.add_argument("--annotations", required=True, type=base.Path)
    args = p.parse_args()

    base.require_artifact(args.graph, base.GRAPH_NAME, base.GRAPH_BYTES, base.GRAPH_SHA256)
    base.require_artifact(
        args.annotations,
        base.ANNOTATION_NAME,
        base.ANNOTATION_BYTES,
        base.ANNOTATION_SHA256,
    )

    traced = base.read_traced_ids(args.annotations)
    original = base.NODE_COUNT
    base.NODE_COUNT = NODE_COUNT
    try:
        selected, traced_rows = base.select_top_degree_traced(args.graph, traced)
    finally:
        base.NODE_COUNT = original

    pre, post, weights = base.extract_subgraph(args.graph, selected)
    results = {}

    for variant in ("R0", "R1", "R2", "R3"):
        runs = [
            sweep.evaluate(
                variant,
                DELAY,
                pre,
                post,
                weights,
                selected.size,
                seed,
            )
            for seed in SEEDS
        ]
        results[variant] = {
            "runs": runs,
            "mean_accuracy": float(np.mean([x["accuracy"] for x in runs])),
            "mean_macro_f1": float(np.mean([x["macro_f1"] for x in runs])),
        }

    diffs = [
        results["R3"]["runs"][i]["macro_f1"] - results["R0"]["runs"][i]["macro_f1"]
        for i in range(len(SEEDS))
    ]
    wins = sum(x > 1e-12 for x in diffs)
    losses = sum(x < -1e-12 for x in diffs)
    ties = len(diffs) - wins - losses

    output = {
        "schema": "panam.public.flycore.scale_replication.v1",
        "scope": "EXPLORATORY_SCALE_REPLICATION_NOT_PRODUCTION",
        "dataset": "MaleCNS v1.0",
        "selection_rule": "top weighted-degree status=Traced neurons; same rule, enlarged cutoff",
        "selected_nodes": int(selected.size),
        "selected_edges": int(pre.size),
        "selected_contact_weight_sum": float(weights.sum()),
        "selected_body_id_sha256": base.hashlib.sha256(selected.tobytes()).hexdigest(),
        "traced_to_traced_edge_rows": int(traced_rows[0]),
        "delay": DELAY,
        "seeds": list(SEEDS),
        "results": results,
        "paired_r3_minus_r0": {
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "mean_difference": float(np.mean(diffs)),
            "median_difference": float(np.median(diffs)),
            "two_sided_exact_sign_test_p": sign_test_two_sided(wins, losses),
            "relative_mean_difference_vs_r0": float(
                (results["R3"]["mean_macro_f1"] - results["R0"]["mean_macro_f1"])
                / results["R0"]["mean_macro_f1"]
            ) if results["R0"]["mean_macro_f1"] > 0 else None,
        },
        "private_panam_data_used": False,
        "production_readiness_claimed": False,
        "promotion_decision": "NOT_MADE",
    }
    print(json.dumps(output, sort_keys=True))
    print("PANAM_PUBLIC_FLYCORE_SCALE_REPLICATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

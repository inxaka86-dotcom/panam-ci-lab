#!/usr/bin/env python3
"""20-new-seed replication of FlyCore linear memory capacity.

This child experiment keeps the exact V1 memory-capacity contract and biological
subgraph, but uses a pre-registered seed set disjoint from the five seeds used
in the parent memory-capacity result.
"""

from __future__ import annotations

import argparse
import json
import math

import numpy as np

import run_real_subgraph_canary as base
import run_delayed_memory_benchmark as mem
import run_linear_memory_capacity as mc

NODE_COUNT = 192
SEEDS = (
    131, 137, 139, 149, 157,
    163, 167, 173, 179, 181,
    191, 193, 197, 199, 211,
    223, 227, 229, 233, 239,
)


def exact_sign_test(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return 1.0
    tail = min(wins, losses)
    return min(1.0, 2.0 * sum(math.comb(n, k) for k in range(tail + 1)) / (2 ** n))


def bootstrap_mean_ci(values, seed=20260920, draws=20000):
    arr = np.asarray(values, dtype=np.float64)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, arr.size, size=(draws, arr.size))
    means = arr[idx].mean(axis=1)
    lo, hi = np.quantile(means, [0.025, 0.975])
    return [float(lo), float(hi)]


def paired(a, b):
    d = np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)
    wins = int(np.sum(d > 1e-12))
    losses = int(np.sum(d < -1e-12))
    ties = int(d.size - wins - losses)
    return {
        "cells": int(d.size),
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "mean_difference": float(d.mean()),
        "median_difference": float(np.median(d)),
        "bootstrap_95pct_mean_ci": bootstrap_mean_ci(d),
        "two_sided_exact_sign_test_p": exact_sign_test(wins, losses),
        "relative_mean_difference_vs_baseline": float(
            (np.mean(a) - np.mean(b)) / np.mean(b)
        ) if np.mean(b) > 0 else None,
    }


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
    old = base.NODE_COUNT
    base.NODE_COUNT = NODE_COUNT
    try:
        selected, traced_rows = base.select_top_degree_traced(args.graph, traced)
    finally:
        base.NODE_COUNT = old
    pre, post, weights = base.extract_subgraph(args.graph, selected)

    variants = {}
    for variant in ("R0", "R1", "R2", "R3"):
        runs = []
        for seed in SEEDS:
            W, swaps = mem.build_memory_matrix(
                variant,
                pre,
                post,
                weights,
                selected.size,
                seed,
            )
            raw = mc.evaluate_variant(W, seed)
            runs.append(
                {
                    "seed": seed,
                    "memory_capacity_1_60": raw["memory_capacity_1_60"],
                    "mc_1_10": raw["mc_1_10"],
                    "mc_11_30": raw["mc_11_30"],
                    "mc_31_60": raw["mc_31_60"],
                    "last_lag_mc_ge_0_1": raw["last_lag_mc_ge_0_1"],
                    "degree_preserving_swaps": swaps,
                }
            )
        variants[variant] = {
            "runs": runs,
            "mean_memory_capacity_1_60": float(np.mean([x["memory_capacity_1_60"] for x in runs])),
            "std_memory_capacity_1_60": float(np.std([x["memory_capacity_1_60"] for x in runs], ddof=1)),
            "mean_mc_1_10": float(np.mean([x["mc_1_10"] for x in runs])),
            "mean_mc_11_30": float(np.mean([x["mc_11_30"] for x in runs])),
            "mean_mc_31_60": float(np.mean([x["mc_31_60"] for x in runs])),
            "mean_last_lag_mc_ge_0_1": float(np.mean([x["last_lag_mc_ge_0_1"] for x in runs])),
        }

    total = {
        k: [x["memory_capacity_1_60"] for x in variants[k]["runs"]]
        for k in variants
    }
    long = {
        k: [x["mc_31_60"] for x in variants[k]["runs"]]
        for k in variants
    }

    output = {
        "schema": "panam.public.flycore.linear_memory_capacity_replication.v1",
        "scope": "NEW_SEED_REPLICATION_NOT_PRODUCTION",
        "dataset": "MaleCNS v1.0",
        "selected_nodes": int(selected.size),
        "selected_edges": int(pre.size),
        "selected_body_id_sha256": base.hashlib.sha256(selected.tobytes()).hexdigest(),
        "traced_to_traced_edge_rows": int(traced_rows[0]),
        "parent_contract_unchanged": {
            "max_lag": mc.MAX_LAG,
            "washout": mc.WASHOUT,
            "train_steps": mc.TRAIN_STEPS,
            "test_steps": mc.TEST_STEPS,
            "leak": mc.LEAK,
            "recurrent_abs_row_sum_target": mem.MEMORY_ROW_SUM,
            "input_scale": mc.INPUT_SCALE,
            "ridge": mc.RIDGE,
        },
        "replication_seeds": list(SEEDS),
        "parent_seed_overlap": [],
        "variants": variants,
        "paired_total_mc": {
            "R3_minus_R0": paired(total["R3"], total["R0"]),
            "R3_minus_R1": paired(total["R3"], total["R1"]),
            "R3_minus_R2": paired(total["R3"], total["R2"]),
        },
        "paired_long_range_mc_31_60": {
            "R3_minus_R0": paired(long["R3"], long["R0"]),
            "R3_minus_R1": paired(long["R3"], long["R1"]),
            "R3_minus_R2": paired(long["R3"], long["R2"]),
        },
        "private_panam_data_used": False,
        "production_readiness_claimed": False,
        "promotion_decision": "NOT_MADE",
        "limitations": [
            "stochastic replication on the same biological subgraph, not independent biological connectomes",
            "single 192-node high-degree selection rule",
            "lag measured only through 60",
            "fixed operating point",
            "R3 uses unsigned contact-count weights",
        ],
    }

    print(json.dumps(output, sort_keys=True))
    print("PANAM_PUBLIC_FLYCORE_LINEAR_MEMORY_REPLICATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

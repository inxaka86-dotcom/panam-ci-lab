#!/usr/bin/env python3
"""Exploratory robustness check for the FlyCore delayed-memory signal.

Uses the same frozen 96-node real MaleCNS subgraph and R0-R3 construction, but
sweeps cue-to-query delay and a larger frozen seed set. Statistics are
descriptive/exploratory and do not authorize promotion or production use.
"""

from __future__ import annotations

import argparse
import json
import math

import numpy as np

import run_real_subgraph_canary as base
import run_delayed_memory_benchmark as mem

SEEDS = (5, 11, 17, 29, 47)
DELAYS = (8, 16, 28, 40)


def delayed_order_dataset(seed: int, per_class: int, delay_steps: int):
    rng = np.random.default_rng(seed)
    cue_pairs = ((0, 1), (1, 0), (2, 3), (3, 2))
    rows = []
    labels = []
    for label, (a, b) in enumerate(cue_pairs):
        for _ in range(per_class):
            prefix = rng.integers(4, 7, size=3, dtype=np.int64)
            gap = rng.integers(4, 7, size=5, dtype=np.int64)
            delay = rng.integers(4, 7, size=delay_steps, dtype=np.int64)
            seq = np.concatenate(
                [prefix, np.array([a]), gap, np.array([b]), delay, np.array([7])]
            )
            rows.append(seq)
            labels.append(label)
    order = rng.permutation(len(rows))
    return np.stack(rows)[order], np.array(labels, dtype=np.int64)[order]


def evaluate(variant, delay, pre, post, weights, n, seed):
    W, swaps = mem.build_memory_matrix(variant, pre, post, weights, n, seed)
    rng = np.random.default_rng(seed + 101)
    Win = rng.normal(0.0, 0.55, size=(n, mem.EVENT_DIM)).astype(np.float32)
    train_seq, train_y = delayed_order_dataset(seed + 201, 40, delay)
    test_seq, test_y = delayed_order_dataset(seed + 1201, 20, delay)

    train_x = mem.reservoir_features(train_seq, W, Win)
    test_x = mem.reservoir_features(test_seq, W, Win)
    readout = mem.ridge_readout(train_x, train_y, 4)
    pred = mem.predict(readout, test_x)
    return {
        "accuracy": float(np.mean(pred == test_y)),
        "macro_f1": mem.macro_f1(test_y, pred, 4),
        "degree_preserving_swaps": swaps,
    }


def sign_test_two_sided(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return 1.0
    tail = min(wins, losses)
    p = 2.0 * sum(math.comb(n, k) for k in range(tail + 1)) / (2 ** n)
    return min(1.0, p)


def bootstrap_mean_ci(values: list[float], seed: int = 20260920):
    arr = np.asarray(values, dtype=np.float64)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, arr.size, size=(10000, arr.size))
    means = arr[idx].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return float(low), float(high)


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
    selected, traced_rows = base.select_top_degree_traced(args.graph, traced)
    pre, post, weights = base.extract_subgraph(args.graph, selected)

    results = {
        variant: {str(delay): [] for delay in DELAYS}
        for variant in ("R0", "R1", "R2", "R3")
    }

    for delay in DELAYS:
        for variant in ("R0", "R1", "R2", "R3"):
            for seed in SEEDS:
                results[variant][str(delay)].append(
                    evaluate(variant, delay, pre, post, weights, selected.size, seed)
                )

    per_delay = {}
    paired_diffs = []
    for delay in DELAYS:
        key = str(delay)
        per_delay[key] = {}
        for variant in ("R0", "R1", "R2", "R3"):
            f1 = [x["macro_f1"] for x in results[variant][key]]
            per_delay[key][variant] = {
                "mean_macro_f1": float(np.mean(f1)),
                "mean_accuracy": float(
                    np.mean([x["accuracy"] for x in results[variant][key]])
                ),
            }
        for i, seed in enumerate(SEEDS):
            paired_diffs.append(
                results["R3"][key][i]["macro_f1"]
                - results["R0"][key][i]["macro_f1"]
            )

    wins = sum(d > 1e-12 for d in paired_diffs)
    losses = sum(d < -1e-12 for d in paired_diffs)
    ties = len(paired_diffs) - wins - losses
    low, high = bootstrap_mean_ci(paired_diffs)

    by_variant = {}
    for variant in ("R0", "R1", "R2", "R3"):
        vals = [
            x["macro_f1"]
            for delay in DELAYS
            for x in results[variant][str(delay)]
        ]
        by_variant[variant] = {
            "mean_macro_f1_across_delay_seed_cells": float(np.mean(vals)),
            "min_macro_f1": float(np.min(vals)),
            "max_macro_f1": float(np.max(vals)),
        }

    r0 = by_variant["R0"]["mean_macro_f1_across_delay_seed_cells"]
    r3 = by_variant["R3"]["mean_macro_f1_across_delay_seed_cells"]

    output = {
        "schema": "panam.public.flycore.delay_sweep_robustness.v1",
        "scope": "EXPLORATORY_ROBUSTNESS_CHILD_NOT_PRODUCTION",
        "dataset": "MaleCNS v1.0",
        "selected_nodes": int(selected.size),
        "selected_edges": int(pre.size),
        "selected_body_id_sha256": base.hashlib.sha256(selected.tobytes()).hexdigest(),
        "traced_to_traced_edge_rows": int(traced_rows[0]),
        "seeds": list(SEEDS),
        "delays": list(DELAYS),
        "task": "delayed_order_4class",
        "per_delay": per_delay,
        "variants": by_variant,
        "paired_r3_minus_r0": {
            "cells": len(paired_diffs),
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "mean_difference": float(np.mean(paired_diffs)),
            "median_difference": float(np.median(paired_diffs)),
            "bootstrap_95pct_mean_ci": [low, high],
            "two_sided_exact_sign_test_p": sign_test_two_sided(wins, losses),
            "relative_mean_difference_vs_r0": float((r3 - r0) / r0) if r0 > 0 else None,
        },
        "limitations": [
            "exploratory statistics",
            "single 96-node task-independent high-degree subgraph",
            "synthetic temporal task",
            "positive contact-count weights without neurotransmitter sign",
            "seed/delay cells share the same graph and are not independent biological replicates",
        ],
        "private_panam_data_used": False,
        "production_readiness_claimed": False,
        "promotion_decision": "NOT_MADE",
    }

    print(json.dumps(output, sort_keys=True))
    print("PANAM_PUBLIC_FLYCORE_DELAY_SWEEP=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Symmetric held-out tuning for R0/R2/R3 on the synthetic PANAM route task.

Purpose: test whether the localized R3 advantage survives when each reservoir
family gets the same bounded hyperparameter-search budget and evaluation is
performed on disjoint seeds.

Public synthetic research only. No real PANAM telemetry is used.
"""

from __future__ import annotations

import argparse
import json
import math

import numpy as np

import run_real_subgraph_canary as base
import run_delayed_memory_benchmark as mem
import run_panam_shaped_temporal_benchmark as panam

NODE_COUNT = 192
VARIANTS = ("R0", "R2", "R3")
VALIDATION_SEEDS = (101, 127, 151)
VALIDATION_DELAYS = (16, 20)
TEST_SEEDS = (181, 211, 241, 271, 307)
TEST_DELAYS = (16, 20, 24)
GAIN_GRID = (0.50, 0.75, 0.95, 1.15)
LEAK_GRID = (0.15, 0.30, 0.45)
EVENT_DIM = panam.EVENT_DIM
INPUT_SCALE = panam.INPUT_SCALE
RIDGE = panam.RIDGE


def scale_matrix(W: np.ndarray, target_abs_row_sum: float) -> np.ndarray:
    row = np.abs(W).sum(axis=1)
    mx = float(row.max())
    if mx <= 0:
        raise RuntimeError("zero_recurrent_matrix")
    return W * np.float32(target_abs_row_sum / mx)


def reservoir_features(seqs: np.ndarray, W: np.ndarray, Win: np.ndarray, leak: float):
    state = np.zeros((seqs.shape[0], W.shape[0]), dtype=np.float32)
    eye = np.eye(EVENT_DIM, dtype=np.float32)
    Wt = W.T
    for t in range(seqs.shape[1]):
        u = eye[seqs[:, t]]
        drive = state @ Wt + u @ Win.T
        state = (1.0 - leak) * state + leak * np.tanh(drive)
    return state.astype(np.float64)


def evaluate(
    W: np.ndarray,
    Win: np.ndarray,
    leak: float,
    seed: int,
    delay: int,
    train_per_class: int,
    test_per_class: int,
):
    train_seq, train_y = panam.route_dataset(
        seed + 20_000,
        per_class=train_per_class,
        delay=delay,
    )
    test_seq, test_y = panam.route_dataset(
        seed + 120_000,
        per_class=test_per_class,
        delay=delay,
    )

    train_x = reservoir_features(train_seq, W, Win, leak)
    test_x = reservoir_features(test_seq, W, Win, leak)
    readout = panam.ridge_readout(train_x, train_y, 4)
    scores = panam.predict_scores(readout, test_x)
    pred = np.argmax(scores, axis=1)
    return {
        "accuracy": float(np.mean(pred == test_y)),
        "macro_f1": panam.macro_f1(test_y, pred, 4),
    }


def exact_sign_test(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return 1.0
    tail = min(wins, losses)
    return min(
        1.0,
        2.0 * sum(math.comb(n, k) for k in range(tail + 1)) / (2 ** n),
    )


def bootstrap_mean_ci(values: list[float], seed: int = 20260920):
    arr = np.asarray(values, dtype=np.float64)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, arr.size, size=(20_000, arr.size))
    means = arr[idx].mean(axis=1)
    lo, hi = np.quantile(means, [0.025, 0.975])
    return [float(lo), float(hi)]


def paired(a: list[float], b: list[float]):
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
        "bootstrap_95pct_mean_ci": bootstrap_mean_ci(d.tolist()),
        "two_sided_exact_sign_test_p": exact_sign_test(wins, losses),
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

    validation_grid = {v: [] for v in VARIANTS}

    for variant in VARIANTS:
        for gain in GAIN_GRID:
            for leak in LEAK_GRID:
                vals = []
                for seed in VALIDATION_SEEDS:
                    rng = np.random.default_rng(seed + 501)
                    Win = rng.normal(
                        0.0,
                        INPUT_SCALE,
                        size=(selected.size, EVENT_DIM),
                    ).astype(np.float32)

                    base_W, _ = mem.build_memory_matrix(
                        variant,
                        pre,
                        post,
                        weights,
                        selected.size,
                        seed,
                    )
                    W = scale_matrix(base_W, gain)

                    for delay in VALIDATION_DELAYS:
                        vals.append(
                            evaluate(
                                W,
                                Win,
                                leak,
                                seed,
                                delay,
                                train_per_class=40,
                                test_per_class=20,
                            )["macro_f1"]
                        )

                validation_grid[variant].append(
                    {
                        "gain": gain,
                        "leak": leak,
                        "validation_mean_macro_f1": float(np.mean(vals)),
                        "validation_min_macro_f1": float(np.min(vals)),
                    }
                )

    chosen = {}
    for variant in VARIANTS:
        ranked = sorted(
            validation_grid[variant],
            key=lambda x: (
                -x["validation_mean_macro_f1"],
                -x["validation_min_macro_f1"],
                x["gain"],
                x["leak"],
            ),
        )
        chosen[variant] = ranked[0]

    test = {v: {"cells": []} for v in VARIANTS}

    for seed in TEST_SEEDS:
        rng = np.random.default_rng(seed + 501)
        Win = rng.normal(
            0.0,
            INPUT_SCALE,
            size=(selected.size, EVENT_DIM),
        ).astype(np.float32)

        for variant in VARIANTS:
            cfg = chosen[variant]
            base_W, _ = mem.build_memory_matrix(
                variant,
                pre,
                post,
                weights,
                selected.size,
                seed,
            )
            W = scale_matrix(base_W, cfg["gain"])

            for delay in TEST_DELAYS:
                result = evaluate(
                    W,
                    Win,
                    cfg["leak"],
                    seed,
                    delay,
                    train_per_class=50,
                    test_per_class=25,
                )
                test[variant]["cells"].append(
                    {
                        "seed": seed,
                        "delay": delay,
                        **result,
                    }
                )

    for variant in VARIANTS:
        cells = test[variant]["cells"]
        test[variant]["mean_macro_f1"] = float(
            np.mean([x["macro_f1"] for x in cells])
        )
        test[variant]["mean_accuracy"] = float(
            np.mean([x["accuracy"] for x in cells])
        )
        by_delay = {}
        for delay in TEST_DELAYS:
            subset = [x for x in cells if x["delay"] == delay]
            by_delay[str(delay)] = {
                "mean_macro_f1": float(
                    np.mean([x["macro_f1"] for x in subset])
                ),
                "mean_accuracy": float(
                    np.mean([x["accuracy"] for x in subset])
                ),
            }
        test[variant]["by_delay"] = by_delay

    f1 = {
        v: [x["macro_f1"] for x in test[v]["cells"]]
        for v in VARIANTS
    }

    output = {
        "schema": "panam.public.flycore.panam_route_tuned_holdout.v1",
        "scope": "SYMMETRIC_TUNED_SYNTHETIC_PANAM_ROUTE_HOLDOUT_NOT_PRODUCTION",
        "dataset": "MaleCNS v1.0",
        "selected_nodes": int(selected.size),
        "selected_edges": int(pre.size),
        "selected_body_id_sha256": base.hashlib.sha256(selected.tobytes()).hexdigest(),
        "traced_to_traced_edge_rows": int(traced_rows[0]),
        "task": "context_route_4class",
        "validation_contract": {
            "seeds": list(VALIDATION_SEEDS),
            "delays": list(VALIDATION_DELAYS),
            "gain_grid": list(GAIN_GRID),
            "leak_grid": list(LEAK_GRID),
            "cells_per_configuration": len(VALIDATION_SEEDS) * len(VALIDATION_DELAYS),
            "same_search_budget_for_each_variant": True,
        },
        "test_contract": {
            "seeds": list(TEST_SEEDS),
            "delays": list(TEST_DELAYS),
            "cells_per_variant": len(TEST_SEEDS) * len(TEST_DELAYS),
            "no_seed_overlap_with_validation": True,
        },
        "chosen": chosen,
        "validation_grid": validation_grid,
        "test": test,
        "paired_r3_minus_r0_holdout_macro_f1": paired(f1["R3"], f1["R0"]),
        "paired_r3_minus_r2_holdout_macro_f1": paired(f1["R3"], f1["R2"]),
        "private_panam_data_used": False,
        "production_readiness_claimed": False,
        "promotion_decision": "NOT_MADE",
        "limitations": [
            "single synthetic PANAM-shaped route task",
            "single weighted-degree 192-node MaleCNS subgraph",
            "bounded grid rather than exhaustive optimization",
            "same biological connectome across variants",
            "unsigned contact-count weights",
        ],
    }

    print(json.dumps(output, sort_keys=True))
    print("PANAM_PUBLIC_FLYCORE_PANAM_ROUTE_TUNED_HOLDOUT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Task-independent linear memory-capacity benchmark for R0-R3.

For each lag k, a linear readout is trained to reconstruct i.i.d. scalar input
u(t-k) from reservoir state x(t). Lag capacity is Pearson correlation squared;
total measured MC is the sum across lags 1..MAX_LAG.

This follows the standard reservoir-computing linear-memory-capacity concept.
"""

from __future__ import annotations

import argparse
import json
import math

import numpy as np

import run_real_subgraph_canary as base
import run_delayed_memory_benchmark as mem

NODE_COUNT = 192
SEEDS = (5, 11, 17, 29, 47)
MAX_LAG = 60
WASHOUT = 250
TRAIN_STEPS = 2500
TEST_STEPS = 1500
LEAK = 0.30
RIDGE = 1e-6
INPUT_SCALE = 0.55


def drive_states(W: np.ndarray, u: np.ndarray, win: np.ndarray) -> np.ndarray:
    n = W.shape[0]
    x = np.zeros(n, dtype=np.float64)
    states = np.zeros((u.size, n), dtype=np.float64)
    W64 = W.astype(np.float64, copy=False)
    for t, val in enumerate(u):
        drive = W64 @ x + win * val
        x = (1.0 - LEAK) * x + LEAK * np.tanh(drive)
        states[t] = x
    return states


def fit_all_lags(states, u, train_start, train_end):
    tids = np.arange(train_start, train_end, dtype=np.int64)
    X = states[tids]
    X = np.concatenate([np.ones((X.shape[0], 1)), X], axis=1)
    Y = np.column_stack([u[tids - k] for k in range(1, MAX_LAG + 1)])

    reg = np.eye(X.shape[1], dtype=np.float64) * RIDGE
    reg[0, 0] = 0.0
    return np.linalg.solve(X.T @ X + reg, X.T @ Y)


def corr2(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    a = a - a.mean()
    b = b - b.mean()
    denom = float(np.sqrt(np.sum(a * a) * np.sum(b * b)))
    if denom <= 0:
        return 0.0
    r = float(np.sum(a * b) / denom)
    return max(0.0, min(1.0, r * r))


def evaluate_variant(W, seed: int):
    rng = np.random.default_rng(seed + 70001)
    total = WASHOUT + MAX_LAG + TRAIN_STEPS + TEST_STEPS
    u = rng.uniform(-1.0, 1.0, size=total).astype(np.float64)
    win = rng.normal(0.0, INPUT_SCALE, size=W.shape[0]).astype(np.float64)

    states = drive_states(W, u, win)
    train_start = WASHOUT + MAX_LAG
    train_end = train_start + TRAIN_STEPS
    test_start = train_end
    test_end = test_start + TEST_STEPS

    readout = fit_all_lags(states, u, train_start, train_end)

    tids = np.arange(test_start, test_end, dtype=np.int64)
    X = states[tids]
    X = np.concatenate([np.ones((X.shape[0], 1)), X], axis=1)
    pred = X @ readout
    target = np.column_stack([u[tids - k] for k in range(1, MAX_LAG + 1)])

    curve = [corr2(target[:, k], pred[:, k]) for k in range(MAX_LAG)]
    return {
        "memory_capacity_1_60": float(np.sum(curve)),
        "mc_1_10": float(np.sum(curve[:10])),
        "mc_11_30": float(np.sum(curve[10:30])),
        "mc_31_60": float(np.sum(curve[30:60])),
        "last_lag_mc_ge_0_5": max([i + 1 for i, v in enumerate(curve) if v >= 0.5], default=0),
        "last_lag_mc_ge_0_1": max([i + 1 for i, v in enumerate(curve) if v >= 0.1], default=0),
        "curve": curve,
    }


def exact_sign_test(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return 1.0
    tail = min(wins, losses)
    return min(1.0, 2.0 * sum(math.comb(n, k) for k in range(tail + 1)) / (2 ** n))


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
            result = evaluate_variant(W, seed)
            result["degree_preserving_swaps"] = swaps
            runs.append(result)

        variants[variant] = {
            "runs": runs,
            "mean_memory_capacity_1_60": float(
                np.mean([r["memory_capacity_1_60"] for r in runs])
            ),
            "mean_mc_1_10": float(np.mean([r["mc_1_10"] for r in runs])),
            "mean_mc_11_30": float(np.mean([r["mc_11_30"] for r in runs])),
            "mean_mc_31_60": float(np.mean([r["mc_31_60"] for r in runs])),
            "mean_last_lag_mc_ge_0_5": float(
                np.mean([r["last_lag_mc_ge_0_5"] for r in runs])
            ),
            "mean_last_lag_mc_ge_0_1": float(
                np.mean([r["last_lag_mc_ge_0_1"] for r in runs])
            ),
        }

    r3 = [r["memory_capacity_1_60"] for r in variants["R3"]["runs"]]
    r0 = [r["memory_capacity_1_60"] for r in variants["R0"]["runs"]]
    diffs = np.asarray(r3) - np.asarray(r0)
    wins = int(np.sum(diffs > 1e-12))
    losses = int(np.sum(diffs < -1e-12))
    ties = int(diffs.size - wins - losses)

    output = {
        "schema": "panam.public.flycore.linear_memory_capacity.v1",
        "scope": "TASK_INDEPENDENT_RESERVOIR_MEMORY_EXPERIMENT_NOT_PRODUCTION",
        "dataset": "MaleCNS v1.0",
        "selected_nodes": int(selected.size),
        "selected_edges": int(pre.size),
        "selected_body_id_sha256": base.hashlib.sha256(selected.tobytes()).hexdigest(),
        "traced_to_traced_edge_rows": int(traced_rows[0]),
        "contract": {
            "seeds": list(SEEDS),
            "max_lag": MAX_LAG,
            "washout": WASHOUT,
            "train_steps": TRAIN_STEPS,
            "test_steps": TEST_STEPS,
            "input_distribution": "iid_uniform_-1_1",
            "leak": LEAK,
            "recurrent_abs_row_sum_target": mem.MEMORY_ROW_SUM,
            "input_scale": INPUT_SCALE,
            "ridge": RIDGE,
            "lag_metric": "squared_Pearson_correlation_on_heldout_test",
            "total_metric": "sum_lag_metric_1_to_60",
        },
        "variants": variants,
        "paired_r3_minus_r0_total_mc": {
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "mean_difference": float(np.mean(diffs)),
            "median_difference": float(np.median(diffs)),
            "relative_mean_difference_vs_r0": float(
                (np.mean(r3) - np.mean(r0)) / np.mean(r0)
            ) if np.mean(r0) > 0 else None,
            "two_sided_exact_sign_test_p": exact_sign_test(wins, losses),
        },
        "private_panam_data_used": False,
        "production_readiness_claimed": False,
        "promotion_decision": "NOT_MADE",
        "limitations": [
            "measured only through lag 60 rather than infinite lag",
            "single 192-node high-degree MaleCNS subgraph",
            "fixed leak/gain operating point inherited from prior memory experiments",
            "five seeds",
            "unsigned contact-count weights for R3",
        ],
    }

    print(json.dumps(output, sort_keys=True))
    print("PANAM_PUBLIC_FLYCORE_LINEAR_MEMORY_CAPACITY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

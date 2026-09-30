#!/usr/bin/env python3
"""Independent NARMA10 benchmark for the refined FlyCore R2-vs-R3 hypothesis.

NARMA10 target:
y[n+1] = 0.3*y[n]
       + 0.05*y[n]*sum(y[n-i], i=0..9)
       + 1.5*u[n-9]*u[n]
       + 0.1

with i.i.d. u ~ Uniform[0, 0.5].

The reservoir state after consuming u[n] predicts y[n+1]. Performance is NMSE
on a held-out continuation. Lower NMSE is better.

Two deterministic MaleCNS selection rules are tested at 192 nodes:
- weighted incident contact-count degree
- unweighted incident traced-to-traced connection-row degree

R2 and R3 share exact topology and weight multiset; R2 permutes weights across
edges while R3 preserves the published edge-to-weight assignment.
"""

from __future__ import annotations

import argparse
import json
import math
import time

import numpy as np

import run_real_subgraph_canary as base
import run_delayed_memory_benchmark as mem
import run_weight_placement_multiscale as multi

NODE_COUNT = 192
SEEDS = (383, 389, 397, 401, 409, 419, 421, 431, 433, 439)
WASHOUT = 250
TRAIN_STEPS = 2500
TEST_STEPS = 1500
INPUT_SCALE = 0.55
LEAK = 0.30
RIDGE = 1e-6


def narma10_input_target(seed: int):
    rng = np.random.default_rng(seed + 120001)
    steps = WASHOUT + TRAIN_STEPS + TEST_STEPS + 20
    u = rng.uniform(0.0, 0.5, size=steps).astype(np.float64)
    y = np.zeros(steps + 1, dtype=np.float64)
    for n in range(9, steps):
        y[n + 1] = (
            0.3 * y[n]
            + 0.05 * y[n] * np.sum(y[n - 9 : n + 1])
            + 1.5 * u[n - 9] * u[n]
            + 0.1
        )
    return u, y


def states_for_input(W: np.ndarray, u: np.ndarray, win: np.ndarray):
    x = np.zeros(W.shape[0], dtype=np.float64)
    states = np.zeros((u.size, W.shape[0]), dtype=np.float64)
    W64 = W.astype(np.float64, copy=False)
    start = time.perf_counter()
    for n, val in enumerate(u):
        drive = W64 @ x + win * val
        x = (1.0 - LEAK) * x + LEAK * np.tanh(drive)
        states[n] = x
    elapsed = time.perf_counter() - start
    return states, elapsed


def fit_readout(X: np.ndarray, target: np.ndarray):
    A = np.concatenate([np.ones((X.shape[0], 1)), X], axis=1)
    reg = np.eye(A.shape[1], dtype=np.float64) * RIDGE
    reg[0, 0] = 0.0
    return np.linalg.solve(A.T @ A + reg, A.T @ target)


def predict_readout(X: np.ndarray, w: np.ndarray):
    A = np.concatenate([np.ones((X.shape[0], 1)), X], axis=1)
    return A @ w


def nmse(target: np.ndarray, pred: np.ndarray) -> float:
    var = float(np.var(target))
    if var <= 0:
        raise RuntimeError("zero_target_variance")
    return float(np.mean((target - pred) ** 2) / var)


def evaluate(W: np.ndarray, seed: int):
    u, y = narma10_input_target(seed)
    rng = np.random.default_rng(seed + 130001)
    win = rng.normal(0.0, INPUT_SCALE, size=W.shape[0]).astype(np.float64)
    states, elapsed = states_for_input(W, u, win)

    train_start = WASHOUT
    train_end = train_start + TRAIN_STEPS
    test_start = train_end
    test_end = test_start + TEST_STEPS

    # state after u[n] -> target y[n+1]
    train_x = states[train_start:train_end]
    train_y = y[train_start + 1 : train_end + 1]
    test_x = states[test_start:test_end]
    test_y = y[test_start + 1 : test_end + 1]

    readout = fit_readout(train_x, train_y)
    pred = predict_readout(test_x, readout)
    score = nmse(test_y, pred)

    return {
        "nmse": score,
        "r2_like_score_1_minus_nmse": float(1.0 - score),
        "state_steps": int(u.size),
        "state_elapsed_seconds": float(elapsed),
        "mean_state_update_microseconds": float(elapsed / u.size * 1e6),
    }


def exact_sign_test(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    tail = min(wins, losses)
    return min(1.0, 2.0 * sum(math.comb(n, k) for k in range(tail + 1)) / (2 ** n))


def bootstrap_ci(values, seed=20260920, draws=20000):
    arr = np.asarray(values, dtype=np.float64)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, arr.size, size=(draws, arr.size))
    means = arr[idx].mean(axis=1)
    lo, hi = np.quantile(means, [0.025, 0.975])
    return [float(lo), float(hi)]


def paired_nmse(r2, r3):
    # Positive means R3 is better because lower NMSE.
    d = np.asarray(r2, dtype=np.float64) - np.asarray(r3, dtype=np.float64)
    wins = int(np.sum(d > 1e-12))
    losses = int(np.sum(d < -1e-12))
    ties = int(d.size - wins - losses)
    return {
        "cells": int(d.size),
        "R3_wins": wins,
        "R3_losses": losses,
        "ties": ties,
        "mean_R2_minus_R3_nmse": float(d.mean()),
        "median_R2_minus_R3_nmse": float(np.median(d)),
        "bootstrap_95pct_mean_difference": bootstrap_ci(d),
        "two_sided_exact_sign_test_p": exact_sign_test(wins, losses),
        "relative_nmse_reduction_R3_vs_R2": float(
            (np.mean(r2) - np.mean(r3)) / np.mean(r2)
        ) if np.mean(r2) > 0 else None,
    }


def run_rule(graph_path, ranked_ids, rule_name):
    selected = np.sort(ranked_ids[:NODE_COUNT])
    pre, post, weights = base.extract_subgraph(graph_path, selected)

    variants = {}
    for variant in ("R2", "R3"):
        runs = []
        for seed in SEEDS:
            W, _ = mem.build_memory_matrix(
                variant,
                pre,
                post,
                weights,
                selected.size,
                seed,
            )
            runs.append({"seed": seed, **evaluate(W, seed)})
        variants[variant] = {
            "runs": runs,
            "mean_nmse": float(np.mean([x["nmse"] for x in runs])),
            "std_nmse": float(np.std([x["nmse"] for x in runs], ddof=1)),
            "mean_state_update_microseconds": float(
                np.mean([x["mean_state_update_microseconds"] for x in runs])
            ),
        }

    r2 = [x["nmse"] for x in variants["R2"]["runs"]]
    r3 = [x["nmse"] for x in variants["R3"]["runs"]]

    return {
        "selection_rule": rule_name,
        "selected_nodes": int(selected.size),
        "selected_edges": int(pre.size),
        "selected_contact_weight_sum": float(weights.sum()),
        "selected_body_id_sha256": base.hashlib.sha256(selected.tobytes()).hexdigest(),
        "variants": variants,
        "paired": paired_nmse(r2, r3),
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
    wrank, _wscore, wrows = multi.weighted_degree_ranking(args.graph, traced)
    urank, _uscore, urows = multi.unweighted_degree_ranking(args.graph, traced)
    if wrows != urows:
        raise RuntimeError("traced_edge_row_count_disagreement")

    results = {
        "weighted_degree": run_rule(args.graph, wrank, "weighted incident contact-count degree"),
        "unweighted_degree": run_rule(args.graph, urank, "unweighted incident connection-row degree"),
    }

    pooled_r2 = []
    pooled_r3 = []
    for x in results.values():
        pooled_r2.extend([r["nmse"] for r in x["variants"]["R2"]["runs"]])
        pooled_r3.extend([r["nmse"] for r in x["variants"]["R3"]["runs"]])

    output = {
        "schema": "panam.public.flycore.narma10_r2_r3.v1",
        "scope": "INDEPENDENT_STANDARD_TEMPORAL_TASK_NOT_PRODUCTION",
        "dataset": "MaleCNS v1.0",
        "task": {
            "name": "NARMA10",
            "input_distribution": "iid_uniform_0_0.5",
            "target_equation": "y[n+1]=0.3*y[n]+0.05*y[n]*sum(y[n-i],i=0..9)+1.5*u[n-9]*u[n]+0.1",
            "primary_metric": "NMSE_lower_is_better",
            "washout": WASHOUT,
            "train_steps": TRAIN_STEPS,
            "test_steps": TEST_STEPS,
        },
        "reservoir_contract": {
            "nodes": NODE_COUNT,
            "seeds": list(SEEDS),
            "seed_overlap_with_prior_memory_experiments": [],
            "leak": LEAK,
            "recurrent_abs_row_sum_target": mem.MEMORY_ROW_SUM,
            "input_scale": INPUT_SCALE,
            "ridge": RIDGE,
        },
        "selection_results": results,
        "pooled_descriptive": {
            **paired_nmse(pooled_r2, pooled_r3),
            "dependence_warning": "two selections share one MaleCNS connectome; pooled cells are descriptive, not independent biological replicates",
        },
        "runtime_note": "state-update wall time is CI-environment observational data, not a portable latency benchmark",
        "private_panam_data_used": False,
        "production_readiness_claimed": False,
        "promotion_decision": "NOT_MADE",
        "limitations": [
            "single MaleCNS connectome",
            "two 192-node high-degree selections",
            "fixed reservoir operating point",
            "dense NumPy implementation",
            "runtime timing includes shared GitHub-hosted runner variability",
            "R3 uses unsigned contact-count strengths",
        ],
    }

    print(json.dumps(output, sort_keys=True))
    print("PANAM_PUBLIC_FLYCORE_NARMA10=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

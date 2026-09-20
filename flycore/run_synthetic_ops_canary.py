#!/usr/bin/env python3
"""Public synthetic PANAM-shaped event-stream canary.

No real PANAM event names, identifiers, logs or topology are used. The fixture
uses generic operational event classes and tests a contextual incident decision:

- an early mode/context cue occurs;
- many distractor events follow;
- a later two-event precursor motif identifies one of two incident mechanisms;
- more distractors follow;
- a final query asks whether the early context and later precursor combination
  should be classified as incident-risk.

The binary target is XOR/equality-like and requires the reservoir to retain
both separated temporal facts while a linear readout makes the final decision.

R0, R2 and R3 are compared under identical inputs/readout/training contracts.
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
SEEDS = (443, 449, 457, 461, 463, 467, 479, 487, 491, 499)
POST_DELAYS = (12, 28)
EVENT_DIM = 10
TRAIN_PER_CLASS = 160
TEST_PER_CLASS = 80
RIDGE = 1e-3

EVENTS = {
    0: "context_a",
    1: "context_b",
    2: "auth_fail",
    3: "repo_change",
    4: "ci_fail",
    5: "service_restart",
    6: "cpu_spike",
    7: "network_error",
    8: "idle",
    9: "query",
}


def make_sequence(rng: np.random.Generator, mode: int, motif: int, post_delay: int):
    # Motif 0: auth_fail -> service_restart
    # Motif 1: repo_change -> cpu_spike
    pair = ((2, 5), (3, 6))[motif]

    prefix = rng.choice([4, 7, 8], size=10, replace=True).astype(np.int64)
    gap = rng.choice([4, 7, 8], size=7, replace=True).astype(np.int64)
    tail = rng.choice([4, 7, 8], size=post_delay, replace=True).astype(np.int64)

    # Add one incomplete opposite-motif decoy so event presence alone is less useful.
    opposite = ((3, 6), (2, 5))[motif]
    if prefix.size:
        prefix[int(rng.integers(0, prefix.size))] = int(opposite[int(rng.integers(0, 2))])
    if tail.size:
        tail[int(rng.integers(0, tail.size))] = int(opposite[int(rng.integers(0, 2))])

    return np.concatenate(
        [
            np.array([mode], dtype=np.int64),
            prefix,
            np.array([pair[0]], dtype=np.int64),
            gap,
            np.array([pair[1]], dtype=np.int64),
            tail,
            np.array([9], dtype=np.int64),
        ]
    )


def dataset(seed: int, per_class: int, post_delay: int):
    rng = np.random.default_rng(seed)
    rows = []
    labels = []

    # Balanced label, balanced mode/motif combinations.
    combos = (
        (0, 0, 1),
        (0, 1, 0),
        (1, 0, 0),
        (1, 1, 1),
    )
    each = per_class // 2
    for mode, motif, label in combos:
        for _ in range(each):
            rows.append(make_sequence(rng, mode, motif, post_delay))
            labels.append(label)

    order = rng.permutation(len(rows))
    return np.stack(rows)[order], np.asarray(labels, dtype=np.int64)[order]


def reservoir_features(seqs: np.ndarray, W: np.ndarray, Win: np.ndarray):
    samples, steps = seqs.shape
    state = np.zeros((samples, W.shape[0]), dtype=np.float32)
    eye = np.eye(EVENT_DIM, dtype=np.float32)

    start = time.perf_counter()
    for t in range(steps):
        u = eye[seqs[:, t]]
        drive = state @ W.T + u @ Win.T
        state = (1.0 - mem.MEMORY_LEAK) * state + mem.MEMORY_LEAK * np.tanh(drive)
    elapsed = time.perf_counter() - start
    return state.astype(np.float64), elapsed


def fit_readout(x, y):
    X = np.concatenate([np.ones((x.shape[0], 1)), x], axis=1)
    Y = np.eye(2, dtype=np.float64)[y]
    reg = np.eye(X.shape[1], dtype=np.float64) * RIDGE
    reg[0, 0] = 0.0
    return np.linalg.solve(X.T @ X + reg, X.T @ Y)


def predict(readout, x):
    X = np.concatenate([np.ones((x.shape[0], 1)), x], axis=1)
    return np.argmax(X @ readout, axis=1)


def macro_f1(y_true, y_pred):
    vals = []
    for k in (0, 1):
        tp = np.sum((y_true == k) & (y_pred == k))
        fp = np.sum((y_true != k) & (y_pred == k))
        fn = np.sum((y_true == k) & (y_pred != k))
        p = float(tp / (tp + fp)) if tp + fp else 0.0
        r = float(tp / (tp + fn)) if tp + fn else 0.0
        vals.append(2 * p * r / (p + r) if p + r else 0.0)
    return float(np.mean(vals))


def evaluate(W, seed: int, post_delay: int):
    rng = np.random.default_rng(seed + 150001)
    Win = rng.normal(0.0, 0.55, size=(W.shape[0], EVENT_DIM)).astype(np.float32)

    train_seq, train_y = dataset(seed + 151001, TRAIN_PER_CLASS, post_delay)
    test_seq, test_y = dataset(seed + 152001, TEST_PER_CLASS, post_delay)

    train_x, train_elapsed = reservoir_features(train_seq, W, Win)
    test_x, test_elapsed = reservoir_features(test_seq, W, Win)
    readout = fit_readout(train_x, train_y)
    pred = predict(readout, test_x)

    return {
        "accuracy": float(np.mean(pred == test_y)),
        "macro_f1": macro_f1(test_y, pred),
        "test_sequence_steps": int(test_seq.shape[1]),
        "test_state_update_seconds": float(test_elapsed),
        "test_microseconds_per_sequence_step": float(
            test_elapsed / (test_seq.shape[0] * test_seq.shape[1]) * 1e6
        ),
        "train_state_update_seconds": float(train_elapsed),
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
        "bootstrap_95pct_mean_difference": bootstrap_ci(d),
        "two_sided_exact_sign_test_p": exact_sign_test(wins, losses),
        "relative_mean_difference_vs_baseline": float(
            (np.mean(a) - np.mean(b)) / np.mean(b)
        ) if np.mean(b) > 0 else None,
    }


def run_rule(graph_path, ranked_ids, name):
    selected = np.sort(ranked_ids[:NODE_COUNT])
    pre, post, weights = base.extract_subgraph(graph_path, selected)

    variants = {}
    for variant in ("R0", "R2", "R3"):
        cells = []
        for delay in POST_DELAYS:
            for seed in SEEDS:
                W, _ = mem.build_memory_matrix(
                    variant,
                    pre,
                    post,
                    weights,
                    selected.size,
                    seed,
                )
                cells.append(
                    {
                        "seed": seed,
                        "post_delay": delay,
                        **evaluate(W, seed, delay),
                    }
                )
        variants[variant] = {
            "cells": cells,
            "mean_macro_f1": float(np.mean([x["macro_f1"] for x in cells])),
            "mean_accuracy": float(np.mean([x["accuracy"] for x in cells])),
            "mean_test_microseconds_per_sequence_step": float(
                np.mean([x["test_microseconds_per_sequence_step"] for x in cells])
            ),
        }

    f1 = {
        k: [x["macro_f1"] for x in variants[k]["cells"]]
        for k in variants
    }
    return {
        "selection_rule": name,
        "selected_nodes": int(selected.size),
        "selected_edges": int(pre.size),
        "selected_body_id_sha256": base.hashlib.sha256(selected.tobytes()).hexdigest(),
        "variants": variants,
        "paired_R3_minus_R0": paired(f1["R3"], f1["R0"]),
        "paired_R3_minus_R2": paired(f1["R3"], f1["R2"]),
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

    output = {
        "schema": "panam.public.flycore.synthetic_ops_contextual_incident.v1",
        "scope": "PUBLIC_SYNTHETIC_PANAM_SHAPED_CANARY_NOT_PRODUCTION",
        "dataset": "MaleCNS v1.0",
        "task": {
            "name": "contextual_incident_risk",
            "description": "early context cue + later ordered operational precursor motif + distractors + final query; target is whether context matches precursor mechanism",
            "event_vocabulary": EVENTS,
            "post_pattern_delays": list(POST_DELAYS),
            "train_per_class": TRAIN_PER_CLASS,
            "test_per_class": TEST_PER_CLASS,
            "private_or_real_panam_events": false,
        },
        "reservoir_contract": {
            "nodes": NODE_COUNT,
            "seeds": list(SEEDS),
            "leak": mem.MEMORY_LEAK,
            "recurrent_abs_row_sum_target": mem.MEMORY_ROW_SUM,
            "ridge": RIDGE,
        },
        "selection_results": {
            "weighted_degree": run_rule(args.graph, wrank, "weighted incident contact-count degree"),
            "unweighted_degree": run_rule(args.graph, urank, "unweighted incident connection-row degree"),
        },
        "runtime_note": "timings are GitHub-hosted CI observations from the same dense NumPy implementation and are not portable production benchmarks",
        "private_panam_data_used": false,
        "production_readiness_claimed": false,
        "promotion_decision": "NOT_MADE",
        "limitations": [
            "synthetic task designed to resemble generic operational event streams only",
            "single MaleCNS connectome",
            "two 192-node high-degree selections",
            "fixed operating point",
            "dense NumPy implementation",
            "one contextual incident task family",
        ],
    }

    print(json.dumps(output, sort_keys=True))
    print("PANAM_PUBLIC_FLYCORE_SYNTHETIC_OPS_CANARY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

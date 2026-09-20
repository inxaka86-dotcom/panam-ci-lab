#!/usr/bin/env python3
"""Synthetic PANAM-shaped temporal benchmark on a real MaleCNS subgraph.

Public research only. Event names imitate broad PANAM telemetry categories but
all sequences are generated synthetically. No production logs, user data,
credentials, repository contents, legal text, hostnames or real incidents are
read by this benchmark.

R0: random topology + permuted connectome-derived weight magnitudes
R1: degree-preserving rewired MaleCNS topology + permuted weights
R2: real MaleCNS topology + permuted weights
R3: real MaleCNS topology + biological placement of published contact weights

The key R3-vs-R2 comparison isolates weight placement on the same topology.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math

import numpy as np

import run_real_subgraph_canary as base
import run_delayed_memory_benchmark as mem

NODE_COUNT = 192
SEEDS = (131, 137, 149, 163, 181)
DELAYS = (16, 24, 32)
EVENT_DIM = 16
LEAK = 0.30
INPUT_SCALE = 0.55
RIDGE = 1e-3

EVENT_VOCAB = {
    0: "AUTH_FAIL",
    1: "PRIVILEGE_CHANGE",
    2: "SERVICE_ERROR",
    3: "CONTAINER_RESTART",
    4: "GIT_PUSH",
    5: "CI_FAILURE",
    6: "SOURCE_UPDATE",
    7: "LARGE_DIFF",
    8: "LOGIN_OK",
    9: "SERVICE_OK",
    10: "HEARTBEAT",
    11: "READ_OK",
    12: "RETRY",
    13: "CACHE_HIT",
    14: "QUEUE_TICK",
    15: "QUERY",
}

NOISE_EVENTS = np.array([10, 11, 12, 13, 14], dtype=np.int64)


def _noise(rng: np.random.Generator, n: int) -> np.ndarray:
    return rng.choice(NOISE_EVENTS, size=n, replace=True).astype(np.int64)


def route_dataset(seed: int, per_class: int, delay: int):
    """Four-way context route after a long common distractor interval."""
    rng = np.random.default_rng(seed)
    cues = (
        (0, 1),  # security
        (2, 3),  # infrastructure
        (4, 5),  # repository
        (6, 7),  # monitoring
    )
    rows, labels = [], []
    for label, pair in enumerate(cues):
        for _ in range(per_class):
            seq = np.concatenate(
                [
                    _noise(rng, 4),
                    np.asarray(pair, dtype=np.int64),
                    _noise(rng, 4),
                    _noise(rng, delay),
                    np.asarray([15], dtype=np.int64),
                ]
            )
            rows.append(seq)
            labels.append(label)
    order = rng.permutation(len(rows))
    return np.stack(rows)[order], np.asarray(labels, dtype=np.int64)[order]


def order_anomaly_dataset(seed: int, per_class: int, delay: int):
    """Binary anomaly: same event multiset, normal vs reversed causal order."""
    rng = np.random.default_rng(seed)
    normal_patterns = ((0, 1, 2), (4, 5, 6))
    anomaly_patterns = tuple(tuple(reversed(x)) for x in normal_patterns)
    rows, labels = [], []

    for label, patterns in ((0, normal_patterns), (1, anomaly_patterns)):
        for _ in range(per_class):
            pattern = patterns[int(rng.integers(0, len(patterns)))]
            seq = np.concatenate(
                [
                    _noise(rng, 4),
                    np.asarray(pattern, dtype=np.int64),
                    _noise(rng, delay),
                    np.asarray([15], dtype=np.int64),
                ]
            )
            rows.append(seq)
            labels.append(label)

    order = rng.permutation(len(rows))
    return np.stack(rows)[order], np.asarray(labels, dtype=np.int64)[order]


def precursor_xor_dataset(seed: int, per_combo: int, delay: int):
    """Cross-channel precursor: label is XOR of two distant subsystem states.

    Security state: AUTH_FAIL vs LOGIN_OK.
    Infrastructure state: SERVICE_ERROR vs SERVICE_OK.
    Both cues occur long before a common QUERY token. This is deliberately
    nonlinear: a linear readout must rely on nonlinear recurrent state mixing.
    """
    rng = np.random.default_rng(seed)
    combos = (
        (8, 9, 0),  # both healthy
        (0, 9, 1),  # security-risk only
        (8, 2, 1),  # infrastructure-risk only
        (0, 2, 0),  # both risky: XOR false
    )
    rows, labels = [], []
    for first, second, label in combos:
        for _ in range(per_combo):
            seq = np.concatenate(
                [
                    _noise(rng, 4),
                    np.asarray([first], dtype=np.int64),
                    _noise(rng, 5),
                    np.asarray([second], dtype=np.int64),
                    _noise(rng, delay),
                    np.asarray([15], dtype=np.int64),
                ]
            )
            rows.append(seq)
            labels.append(label)
    order = rng.permutation(len(rows))
    return np.stack(rows)[order], np.asarray(labels, dtype=np.int64)[order]


def reservoir_features(seqs: np.ndarray, W: np.ndarray, Win: np.ndarray):
    samples, steps = seqs.shape
    state = np.zeros((samples, W.shape[0]), dtype=np.float32)
    eye = np.eye(EVENT_DIM, dtype=np.float32)
    Wt = W.T
    for t in range(steps):
        u = eye[seqs[:, t]]
        drive = state @ Wt + u @ Win.T
        state = (1.0 - LEAK) * state + LEAK * np.tanh(drive)
    return state.astype(np.float64)


def ridge_readout(train_x, train_y, classes: int):
    X = np.concatenate([np.ones((train_x.shape[0], 1)), train_x], axis=1)
    Y = np.eye(classes, dtype=np.float64)[train_y]
    reg = np.eye(X.shape[1], dtype=np.float64) * RIDGE
    reg[0, 0] = 0.0
    return np.linalg.solve(X.T @ X + reg, X.T @ Y)


def predict_scores(readout, x):
    X = np.concatenate([np.ones((x.shape[0], 1)), x], axis=1)
    return X @ readout


def macro_f1(y_true: np.ndarray, y_pred: np.ndarray, classes: int) -> float:
    vals = []
    for k in range(classes):
        tp = int(np.sum((y_true == k) & (y_pred == k)))
        fp = int(np.sum((y_true != k) & (y_pred == k)))
        fn = int(np.sum((y_true == k) & (y_pred != k)))
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        vals.append(2.0 * p * r / (p + r) if p + r else 0.0)
    return float(np.mean(vals))


def average_precision_binary(y_true: np.ndarray, score: np.ndarray) -> float:
    order = np.argsort(-score, kind="stable")
    y = y_true[order]
    positives = int(np.sum(y == 1))
    if positives == 0:
        return 0.0
    tp = 0
    acc = 0.0
    for rank, label in enumerate(y, start=1):
        if label == 1:
            tp += 1
            acc += tp / rank
    return float(acc / positives)


def make_task(task: str, seed: int, train: bool, delay: int):
    offset = 0 if train else 100_000
    s = seed + offset
    if task == "context_route_4class":
        return route_dataset(s, per_class=50 if train else 25, delay=delay), 4
    if task == "order_anomaly_binary":
        return order_anomaly_dataset(s, per_class=100 if train else 50, delay=delay), 2
    if task == "cross_channel_precursor_xor":
        return precursor_xor_dataset(s, per_combo=50 if train else 25, delay=delay), 2
    raise ValueError(task)


def evaluate_task(W, Win, task: str, seed: int, delay: int):
    (train_seq, train_y), classes = make_task(task, seed + 2_000, True, delay)
    (test_seq, test_y), test_classes = make_task(task, seed + 2_000, False, delay)
    if classes != test_classes:
        raise RuntimeError("class_contract_mismatch")

    train_x = reservoir_features(train_seq, W, Win)
    test_x = reservoir_features(test_seq, W, Win)
    readout = ridge_readout(train_x, train_y, classes)
    scores = predict_scores(readout, test_x)
    pred = np.argmax(scores, axis=1)

    out = {
        "accuracy": float(np.mean(pred == test_y)),
        "macro_f1": macro_f1(test_y, pred, classes),
    }
    if classes == 2:
        out["average_precision_positive"] = average_precision_binary(
            test_y, scores[:, 1]
        )
    return out


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


def paired_summary(a: list[float], b: list[float]):
    diffs = np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)
    wins = int(np.sum(diffs > 1e-12))
    losses = int(np.sum(diffs < -1e-12))
    ties = int(diffs.size - wins - losses)
    return {
        "cells": int(diffs.size),
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "mean_difference": float(np.mean(diffs)),
        "median_difference": float(np.median(diffs)),
        "bootstrap_95pct_mean_ci": bootstrap_mean_ci(diffs.tolist()),
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
    old_count = base.NODE_COUNT
    base.NODE_COUNT = NODE_COUNT
    try:
        selected, traced_rows = base.select_top_degree_traced(args.graph, traced)
    finally:
        base.NODE_COUNT = old_count
    pre, post, weights = base.extract_subgraph(args.graph, selected)

    tasks = (
        "context_route_4class",
        "order_anomaly_binary",
        "cross_channel_precursor_xor",
    )
    variants = ("R0", "R1", "R2", "R3")
    cells = {
        task: {
            str(delay): {variant: [] for variant in variants}
            for delay in DELAYS
        }
        for task in tasks
    }

    for seed in SEEDS:
        rng = np.random.default_rng(seed + 501)
        Win = rng.normal(
            0.0,
            INPUT_SCALE,
            size=(selected.size, EVENT_DIM),
        ).astype(np.float32)

        matrices = {}
        for variant in variants:
            W, _ = mem.build_memory_matrix(
                variant,
                pre,
                post,
                weights,
                selected.size,
                seed,
            )
            matrices[variant] = W

        for delay in DELAYS:
            for task in tasks:
                for variant in variants:
                    result = evaluate_task(
                        matrices[variant],
                        Win,
                        task,
                        seed,
                        delay,
                    )
                    cells[task][str(delay)][variant].append(result)

    task_summary = {}
    pooled_f1 = {variant: [] for variant in variants}
    pooled_r3 = []
    pooled_r2 = []
    pooled_r0 = []

    for task in tasks:
        task_summary[task] = {}
        for delay in DELAYS:
            key = str(delay)
            task_summary[task][key] = {}
            for variant in variants:
                runs = cells[task][key][variant]
                f1s = [x["macro_f1"] for x in runs]
                pooled_f1[variant].extend(f1s)
                entry = {
                    "mean_accuracy": float(np.mean([x["accuracy"] for x in runs])),
                    "mean_macro_f1": float(np.mean(f1s)),
                    "runs": runs,
                }
                aps = [
                    x["average_precision_positive"]
                    for x in runs
                    if "average_precision_positive" in x
                ]
                if aps:
                    entry["mean_average_precision_positive"] = float(np.mean(aps))
                task_summary[task][key][variant] = entry

            pooled_r3.extend(
                x["macro_f1"] for x in cells[task][key]["R3"]
            )
            pooled_r2.extend(
                x["macro_f1"] for x in cells[task][key]["R2"]
            )
            pooled_r0.extend(
                x["macro_f1"] for x in cells[task][key]["R0"]
            )

    aggregate = {
        variant: {
            "mean_macro_f1_across_task_delay_seed_cells": float(
                np.mean(pooled_f1[variant])
            ),
            "min_macro_f1": float(np.min(pooled_f1[variant])),
            "max_macro_f1": float(np.max(pooled_f1[variant])),
        }
        for variant in variants
    }

    output = {
        "schema": "panam.public.flycore.panam_shaped_temporal_benchmark.v1",
        "scope": "SYNTHETIC_PANAM_SHAPED_PUBLIC_RESEARCH_NOT_PRODUCTION",
        "dataset": "MaleCNS v1.0",
        "selected_nodes": int(selected.size),
        "selected_edges": int(pre.size),
        "selected_contact_weight_sum": float(weights.sum()),
        "selected_body_id_sha256": hashlib.sha256(selected.tobytes()).hexdigest(),
        "selection_rule": "top 192 status=Traced neurons by weighted incident contact-count degree; task-independent",
        "traced_to_traced_edge_rows": int(traced_rows[0]),
        "event_vocabulary": {str(k): v for k, v in EVENT_VOCAB.items()},
        "synthetic_only": True,
        "private_panam_data_used": False,
        "production_logs_used": False,
        "credentials_used": False,
        "tasks": {
            "context_route_4class": {
                "description": "route a common QUERY using domain cues retained across distractor events",
                "classes": ["security", "infrastructure", "repository", "monitoring"],
            },
            "order_anomaly_binary": {
                "description": "detect reversed causal order with the same event multiset",
                "positive_class": "anomalous_order",
            },
            "cross_channel_precursor_xor": {
                "description": "detect a nonlinear long-range inconsistency between security and infrastructure state cues",
                "positive_class": "cross_channel_precursor",
            },
        },
        "contract": {
            "seeds": list(SEEDS),
            "delays": list(DELAYS),
            "event_dim": EVENT_DIM,
            "leak": LEAK,
            "input_scale": INPUT_SCALE,
            "ridge": RIDGE,
            "same_dataset_and_input_projection_across_R0_R1_R2_R3": True,
        },
        "results": task_summary,
        "aggregate": aggregate,
        "paired_r3_minus_r2_macro_f1": paired_summary(pooled_r3, pooled_r2),
        "paired_r3_minus_r0_macro_f1": paired_summary(pooled_r3, pooled_r0),
        "promotion_decision": "NOT_MADE",
        "production_readiness_claimed": False,
        "limitations": [
            "all PANAM-shaped events are synthetic abstractions, not real PANAM telemetry",
            "single MaleCNS connectome and one task-independent 192-node selection",
            "three task families share one synthetic event vocabulary",
            "fixed reservoir operating point rather than per-variant tuning",
            "seed/delay/task cells share one biological graph and are not independent biological replicates",
            "unsigned contact-count weights",
        ],
    }

    print(json.dumps(output, sort_keys=True))
    print("PANAM_PUBLIC_FLYCORE_PANAM_SHAPED_TEMPORAL_BENCHMARK=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

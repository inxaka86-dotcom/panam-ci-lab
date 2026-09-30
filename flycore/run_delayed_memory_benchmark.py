#!/usr/bin/env python3
"""Child benchmark: delayed-memory tasks on the frozen real MaleCNS subgraph.

Parent canary saturated at F1=1.0 for all variants, so it was non-discriminative.
This child keeps the same graph-selection rule and R0-R3 semantics, but moves
the task-relevant cues far before a final query event and inserts distractors.
"""

from __future__ import annotations

import argparse
import json

import numpy as np

import run_real_subgraph_canary as base

EVENT_DIM = 8
MEMORY_ROW_SUM = 0.95
MEMORY_LEAK = 0.30
RIDGE = 1e-2
SEEDS = (11, 29, 47)


def reservoir_features(seqs: np.ndarray, W: np.ndarray, Win: np.ndarray):
    samples, steps = seqs.shape
    n = W.shape[0]
    state = np.zeros((samples, n), dtype=np.float32)
    eye = np.eye(EVENT_DIM, dtype=np.float32)
    for t in range(steps):
        u = eye[seqs[:, t]]
        drive = state @ W.T + u @ Win.T
        state = (1.0 - MEMORY_LEAK) * state + MEMORY_LEAK * np.tanh(drive)
    return state.astype(np.float64)


def ridge_readout(train_x, train_y, classes: int):
    X = np.concatenate([np.ones((train_x.shape[0], 1)), train_x], axis=1)
    Y = np.eye(classes, dtype=np.float64)[train_y]
    reg = np.eye(X.shape[1], dtype=np.float64) * RIDGE
    reg[0, 0] = 0.0
    return np.linalg.solve(X.T @ X + reg, X.T @ Y)


def predict(readout, x):
    X = np.concatenate([np.ones((x.shape[0], 1)), x], axis=1)
    return np.argmax(X @ readout, axis=1)


def macro_f1(y_true: np.ndarray, y_pred: np.ndarray, classes: int) -> float:
    vals = []
    for k in range(classes):
        tp = np.sum((y_true == k) & (y_pred == k))
        fp = np.sum((y_true != k) & (y_pred == k))
        fn = np.sum((y_true == k) & (y_pred != k))
        p = float(tp / (tp + fp)) if tp + fp else 0.0
        r = float(tp / (tp + fn)) if tp + fn else 0.0
        vals.append(2 * p * r / (p + r) if p + r else 0.0)
    return float(np.mean(vals))


def delayed_order_dataset(seed: int, per_class: int):
    rng = np.random.default_rng(seed)
    cue_pairs = ((0, 1), (1, 0), (2, 3), (3, 2))
    rows = []
    labels = []
    for label, (a, b) in enumerate(cue_pairs):
        for _ in range(per_class):
            prefix = rng.integers(4, 7, size=3, dtype=np.int64)
            gap = rng.integers(4, 7, size=5, dtype=np.int64)
            delay = rng.integers(4, 7, size=28, dtype=np.int64)
            seq = np.concatenate(
                [prefix, np.array([a]), gap, np.array([b]), delay, np.array([7])]
            )
            rows.append(seq)
            labels.append(label)
    order = rng.permutation(len(rows))
    return np.stack(rows)[order], np.array(labels, dtype=np.int64)[order]


def delayed_xor_dataset(seed: int, per_combo: int):
    rng = np.random.default_rng(seed)
    rows = []
    labels = []
    combos = ((0, 2, 0), (0, 3, 1), (1, 2, 1), (1, 3, 0))
    for a, b, label in combos:
        for _ in range(per_combo):
            prefix = rng.integers(4, 7, size=3, dtype=np.int64)
            gap = rng.integers(4, 7, size=5, dtype=np.int64)
            delay = rng.integers(4, 7, size=28, dtype=np.int64)
            seq = np.concatenate(
                [prefix, np.array([a]), gap, np.array([b]), delay, np.array([7])]
            )
            rows.append(seq)
            labels.append(label)
    order = rng.permutation(len(rows))
    return np.stack(rows)[order], np.array(labels, dtype=np.int64)[order]


def build_memory_matrix(variant, pre, post, weights, n, seed):
    W, swaps = base.build_matrix(variant, pre, post, weights, n, seed)
    W = W * np.float32(MEMORY_ROW_SUM / base.RECURRENT_ROW_SUM)
    return W, swaps


def evaluate_task(variant, task, pre, post, weights, n, seed):
    W, swaps = build_memory_matrix(variant, pre, post, weights, n, seed)
    rng = np.random.default_rng(seed + 101)
    Win = rng.normal(0.0, 0.55, size=(n, EVENT_DIM)).astype(np.float32)

    if task == "delayed_order_4class":
        train_seq, train_y = delayed_order_dataset(seed + 201, per_class=60)
        test_seq, test_y = delayed_order_dataset(seed + 1201, per_class=30)
        classes = 4
    elif task == "delayed_xor_binary":
        train_seq, train_y = delayed_xor_dataset(seed + 301, per_combo=60)
        test_seq, test_y = delayed_xor_dataset(seed + 1301, per_combo=30)
        classes = 2
    else:
        raise ValueError(task)

    train_x = reservoir_features(train_seq, W, Win)
    test_x = reservoir_features(test_seq, W, Win)
    readout = ridge_readout(train_x, train_y, classes)
    pred = predict(readout, test_x)
    return {
        "accuracy": float(np.mean(pred == test_y)),
        "macro_f1": macro_f1(test_y, pred, classes),
        "degree_preserving_swaps": swaps,
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
    selected, traced_rows = base.select_top_degree_traced(args.graph, traced)
    pre, post, weights = base.extract_subgraph(args.graph, selected)

    tasks = ("delayed_order_4class", "delayed_xor_binary")
    result = {
        "schema": "panam.public.flycore.delayed_memory_benchmark.v1",
        "parent_result": "SATURATED_NON_DISCRIMINATIVE_TASK",
        "scope": "BOUNDED_REAL_CONNECTOME_CHILD_EXPERIMENT_NOT_PRODUCTION",
        "scientific_result": True,
        "dataset": "MaleCNS v1.0",
        "selection_rule": "same frozen rule as parent: top weighted-degree status=Traced neurons; task-independent",
        "selected_body_id_sha256": base.hashlib.sha256(selected.tobytes()).hexdigest(),
        "selected_nodes": int(selected.size),
        "selected_edges": int(pre.size),
        "traced_to_traced_edge_rows": int(traced_rows[0]),
        "memory_contract": {
            "row_sum_target": MEMORY_ROW_SUM,
            "leak": MEMORY_LEAK,
            "cue_to_query_distractor_steps": 28,
            "query_event": 7,
            "distractor_event_set": [4, 5, 6],
        },
        "seeds": list(SEEDS),
        "tasks": {},
        "variants": {},
        "private_panam_data_used": False,
        "credentials_used_for_dataset": False,
        "autonomous_action": False,
        "production_readiness_claimed": False,
    }

    for task in tasks:
        result["tasks"][task] = {}
        for variant in ("R0", "R1", "R2", "R3"):
            runs = [
                evaluate_task(variant, task, pre, post, weights, selected.size, seed)
                for seed in SEEDS
            ]
            result["tasks"][task][variant] = {
                "runs": runs,
                "mean_accuracy": float(np.mean([x["accuracy"] for x in runs])),
                "mean_macro_f1": float(np.mean([x["macro_f1"] for x in runs])),
            }

    for variant in ("R0", "R1", "R2", "R3"):
        f1s = [
            result["tasks"][task][variant]["mean_macro_f1"]
            for task in tasks
        ]
        result["variants"][variant] = {
            "mean_macro_f1_across_tasks": float(np.mean(f1s))
        }

    r0 = result["variants"]["R0"]["mean_macro_f1_across_tasks"]
    r3 = result["variants"]["R3"]["mean_macro_f1_across_tasks"]
    result["r3_minus_r0_macro_f1"] = float(r3 - r0)
    result["relative_r3_vs_r0"] = float((r3 - r0) / r0) if r0 > 0 else None

    print(json.dumps(result, sort_keys=True))
    print("PANAM_PUBLIC_FLYCORE_DELAYED_MEMORY_BENCHMARK=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

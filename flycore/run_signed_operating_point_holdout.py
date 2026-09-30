#!/usr/bin/env python3
"""Held-out operating-point test for conservative signed FlyCore.

Question: did AG_SIGNED lose merely because it inherited leak/gain chosen for
the unsigned reservoir?

Method:
- same frozen 192-node task-independent MaleCNS subgraph;
- same ACh/GABA mask for AG_ABS and AG_SIGNED;
- identical finite hyperparameter grid for both modes;
- select each mode's best leak/gain on validation cells only;
- evaluate once on distinct held-out seeds and delays.

This is exploratory model-selection evidence, not production validation.
"""

from __future__ import annotations

import argparse
import json
import math

import numpy as np

import run_real_subgraph_canary as base
import run_delay_sweep_robustness as sweep
import run_delayed_memory_benchmark as mem
import run_conservative_signed_nt as signed

NODE_COUNT = 192
LEAK_GRID = (0.15, 0.30, 0.50, 0.70)
GAIN_GRID = (0.50, 0.75, 1.00, 1.25)

VALIDATION_SEEDS = (101, 131, 151)
VALIDATION_DELAYS = (12, 20)

TEST_SEEDS = (181, 211, 241, 271, 307)
TEST_DELAYS = (16, 24, 32)


def raw_ag_matrices(pre, post, weights, nts, n):
    source_class = np.zeros(n, dtype=np.int8)
    for i, nt in enumerate(nts):
        if nt == "acetylcholine":
            source_class[i] = 1
        elif nt == "gaba":
            source_class[i] = -1

    mask = source_class[pre] != 0
    ap = pre[mask]
    aq = post[mask]
    aw = np.log1p(weights[mask]).astype(np.float32)

    abs_w = np.zeros((n, n), dtype=np.float32)
    signed_w = np.zeros((n, n), dtype=np.float32)

    np.add.at(abs_w, (aq, ap), aw)
    np.add.at(
        signed_w,
        (aq, ap),
        aw * source_class[ap].astype(np.float32),
    )

    if not np.any(abs_w) or not np.any(signed_w):
        raise RuntimeError("empty_ag_matrix")
    return {"AG_ABS": abs_w, "AG_SIGNED": signed_w}


def scale_matrix(raw: np.ndarray, gain: float) -> np.ndarray:
    mx = float(np.abs(raw).sum(axis=1).max())
    if mx <= 0:
        raise RuntimeError("zero_matrix_norm")
    return raw * np.float32(gain / mx)


def reservoir_features(seqs, W, Win, leak):
    samples, steps = seqs.shape
    n = W.shape[0]
    state = np.zeros((samples, n), dtype=np.float32)
    eye = np.eye(mem.EVENT_DIM, dtype=np.float32)
    for t in range(steps):
        u = eye[seqs[:, t]]
        drive = state @ W.T + u @ Win.T
        state = (1.0 - leak) * state + leak * np.tanh(drive)
    return state.astype(np.float64)


def evaluate_cell(raw, leak, gain, seed, delay):
    W = scale_matrix(raw, gain)
    rng = np.random.default_rng(seed + 101)
    Win = rng.normal(0.0, 0.55, size=(W.shape[0], mem.EVENT_DIM)).astype(np.float32)

    train_seq, train_y = sweep.delayed_order_dataset(seed + 201, 40, delay)
    test_seq, test_y = sweep.delayed_order_dataset(seed + 1201, 20, delay)

    train_x = reservoir_features(train_seq, W, Win, leak)
    test_x = reservoir_features(test_seq, W, Win, leak)
    readout = mem.ridge_readout(train_x, train_y, 4)
    pred = mem.predict(readout, test_x)
    return {
        "accuracy": float(np.mean(pred == test_y)),
        "macro_f1": mem.macro_f1(test_y, pred, 4),
    }


def score_grid(raw):
    rows = []
    for leak in LEAK_GRID:
        for gain in GAIN_GRID:
            vals = []
            for delay in VALIDATION_DELAYS:
                for seed in VALIDATION_SEEDS:
                    vals.append(evaluate_cell(raw, leak, gain, seed, delay)["macro_f1"])
            rows.append(
                {
                    "leak": leak,
                    "gain": gain,
                    "validation_mean_macro_f1": float(np.mean(vals)),
                    "validation_min_macro_f1": float(np.min(vals)),
                }
            )
    # deterministic tie-break: max score, then lower gain, then lower leak
    rows.sort(
        key=lambda r: (
            -r["validation_mean_macro_f1"],
            r["gain"],
            r["leak"],
        )
    )
    return rows[0], rows


def exact_sign_test(wins, losses):
    n = wins + losses
    if n == 0:
        return 1.0
    tail = min(wins, losses)
    return min(1.0, 2.0 * sum(math.comb(n, k) for k in range(tail + 1)) / (2 ** n))


def test_selected(raw, selected):
    cells = []
    for delay in TEST_DELAYS:
        for seed in TEST_SEEDS:
            result = evaluate_cell(
                raw,
                selected["leak"],
                selected["gain"],
                seed,
                delay,
            )
            cells.append({"delay": delay, "seed": seed, **result})
    return cells


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--graph", required=True, type=base.Path)
    p.add_argument("--annotations", required=True, type=base.Path)
    p.add_argument("--neurotransmitters", required=True, type=base.Path)
    args = p.parse_args()

    base.require_artifact(args.graph, base.GRAPH_NAME, base.GRAPH_BYTES, base.GRAPH_SHA256)
    base.require_artifact(
        args.annotations,
        base.ANNOTATION_NAME,
        base.ANNOTATION_BYTES,
        base.ANNOTATION_SHA256,
    )
    base.require_artifact(
        args.neurotransmitters,
        signed.NT_NAME,
        signed.NT_BYTES,
        signed.NT_SHA256,
    )

    traced = base.read_traced_ids(args.annotations)
    old = base.NODE_COUNT
    base.NODE_COUNT = NODE_COUNT
    try:
        selected_ids, traced_rows = base.select_top_degree_traced(args.graph, traced)
    finally:
        base.NODE_COUNT = old
    pre, post, weights = base.extract_subgraph(args.graph, selected_ids)
    nts, nt_counts = signed.read_consensus_nt(args.neurotransmitters, selected_ids)
    raw = raw_ag_matrices(pre, post, weights, nts, selected_ids.size)

    chosen = {}
    grids = {}
    tests = {}
    for mode in ("AG_ABS", "AG_SIGNED"):
        best, grid = score_grid(raw[mode])
        chosen[mode] = best
        grids[mode] = grid
        tests[mode] = test_selected(raw[mode], best)

    abs_vals = [x["macro_f1"] for x in tests["AG_ABS"]]
    signed_vals = [x["macro_f1"] for x in tests["AG_SIGNED"]]
    diffs = np.asarray(signed_vals) - np.asarray(abs_vals)
    wins = int(np.sum(diffs > 1e-12))
    losses = int(np.sum(diffs < -1e-12))
    ties = int(diffs.size - wins - losses)

    output = {
        "schema": "panam.public.flycore.signed_operating_point_holdout.v1",
        "scope": "EXPLORATORY_HELD_OUT_MODEL_SELECTION_NOT_PRODUCTION",
        "dataset": "MaleCNS v1.0",
        "selected_nodes": int(selected_ids.size),
        "selected_edges": int(pre.size),
        "selected_body_id_sha256": base.hashlib.sha256(selected_ids.tobytes()).hexdigest(),
        "selected_consensus_nt_counts": nt_counts,
        "validation_contract": {
            "seeds": list(VALIDATION_SEEDS),
            "delays": list(VALIDATION_DELAYS),
            "leak_grid": list(LEAK_GRID),
            "gain_grid": list(GAIN_GRID),
            "cells_per_configuration": len(VALIDATION_SEEDS) * len(VALIDATION_DELAYS),
        },
        "test_contract": {
            "seeds": list(TEST_SEEDS),
            "delays": list(TEST_DELAYS),
            "cells_per_mode": len(TEST_SEEDS) * len(TEST_DELAYS),
        },
        "chosen": chosen,
        "validation_grid": grids,
        "test": {
            mode: {
                "cells": tests[mode],
                "mean_macro_f1": float(np.mean([x["macro_f1"] for x in tests[mode]])),
                "mean_accuracy": float(np.mean([x["accuracy"] for x in tests[mode]])),
            }
            for mode in ("AG_ABS", "AG_SIGNED")
        },
        "paired_signed_minus_abs_on_holdout": {
            "cells": int(diffs.size),
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "mean_difference": float(diffs.mean()),
            "median_difference": float(np.median(diffs)),
            "two_sided_exact_sign_test_p": exact_sign_test(wins, losses),
        },
        "private_panam_data_used": False,
        "production_readiness_claimed": False,
        "promotion_decision": "NOT_MADE",
        "limitations": [
            "small bounded hyperparameter grid",
            "only ACh/GABA binary sign modeled",
            "postsynaptic receptor identity/state absent",
            "single 192-node high-degree biological subgraph",
            "synthetic task family",
        ],
    }

    print(json.dumps(output, sort_keys=True))
    print("PANAM_PUBLIC_FLYCORE_SIGNED_HOLDOUT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

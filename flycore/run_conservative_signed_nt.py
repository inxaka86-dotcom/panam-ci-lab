#!/usr/bin/env python3
"""Conservative signed-transmitter FlyCore experiment.

The experiment uses only the two Drosophila transmitter classes with a clear
fast-sign interpretation for this purpose:
- acetylcholine: positive/excitatory
- GABA: negative/inhibitory

Glutamate, histamine, dopamine, serotonin, octopamine and unclear predictions
are excluded from the signed-core comparison rather than assigned an arbitrary
binary sign.

Comparison is performed on the identical ACh/GABA edge mask:
  AG_ABS          -> all retained weights positive
  AG_SIGNED       -> ACh positive, GABA negative
  AG_SIGN_SHUFFLE -> same count of positive/negative presynaptic labels, shuffled

The full unsigned R3 graph is reported for context only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math

import numpy as np
import pyarrow.feather as feather

import run_real_subgraph_canary as base
import run_delay_sweep_robustness as sweep
import run_delayed_memory_benchmark as mem

NT_NAME = "body-neurotransmitters-male-cns-v1.0.feather"
NT_BYTES = 43_282_834
NT_SHA256 = "95c9289220663abeb3409f3ad9e5a7f8a53f8093f5139d15502cd08da8879621"
NT_ROWS = 1_835_518

NODE_COUNT = 192
SEEDS = (5, 11, 17, 29, 47)
DELAYS = (12, 16, 20, 28)


def read_consensus_nt(path, selected_ids: np.ndarray) -> tuple[list[str], dict[str, int]]:
    base.require_artifact(path, NT_NAME, NT_BYTES, NT_SHA256)
    table = feather.read_table(
        path,
        columns=["body", "consensus_nt"],
        memory_map=True,
    )
    if table.num_rows != NT_ROWS:
        raise RuntimeError(f"nt_row_count_mismatch:{table.num_rows}")

    body = table["body"].to_numpy(zero_copy_only=False).astype(np.int64, copy=False)
    consensus = np.array(table["consensus_nt"].to_pylist(), dtype=object)

    order = np.argsort(body, kind="stable")
    sb = body[order]
    if np.any(sb[1:] == sb[:-1]):
        raise RuntimeError("duplicate_body_in_nt_table")
    sc = consensus[order]

    idx = np.searchsorted(sb, selected_ids)
    valid = (idx < sb.size) & (sb[np.minimum(idx, sb.size - 1)] == selected_ids)
    if not np.all(valid):
        missing = int((~valid).sum())
        raise RuntimeError(f"selected_body_missing_nt:{missing}")

    nts = [
        "unclear" if sc[i] is None else str(sc[i]).lower()
        for i in idx
    ]
    counts = {}
    for nt in nts:
        counts[nt] = counts.get(nt, 0) + 1
    return nts, dict(sorted(counts.items()))


def normalize(W: np.ndarray) -> np.ndarray:
    row_sum = np.abs(W).sum(axis=1)
    mx = float(row_sum.max())
    if mx <= 0:
        raise RuntimeError("zero_signed_matrix")
    return W * np.float32(mem.MEMORY_ROW_SUM / mx)


def matrix_from_edge_signs(
    pre: np.ndarray,
    post: np.ndarray,
    weights: np.ndarray,
    n: int,
    source_sign: np.ndarray,
) -> np.ndarray:
    W = np.zeros((n, n), dtype=np.float32)
    signed = np.log1p(weights).astype(np.float32) * source_sign[pre].astype(np.float32)
    np.add.at(W, (post, pre), signed)
    return normalize(W)


def build_ag_matrices(
    pre: np.ndarray,
    post: np.ndarray,
    weights: np.ndarray,
    nts: list[str],
    n: int,
    seed: int,
):
    source_class = np.zeros(n, dtype=np.int8)
    for i, nt in enumerate(nts):
        if nt == "acetylcholine":
            source_class[i] = 1
        elif nt == "gaba":
            source_class[i] = -1

    mask = source_class[pre] != 0
    ap = pre[mask]
    aq = post[mask]
    aw = weights[mask]
    if ap.size == 0:
        raise RuntimeError("no_ach_gaba_edges")

    abs_sign = np.ones(n, dtype=np.float32)
    bio_sign = source_class.astype(np.float32)

    eligible_nodes = np.flatnonzero(source_class != 0)
    shuffled_values = source_class[eligible_nodes].copy()
    rng = np.random.default_rng(seed + 9001)
    rng.shuffle(shuffled_values)
    shuffled_sign = np.zeros(n, dtype=np.float32)
    shuffled_sign[eligible_nodes] = shuffled_values.astype(np.float32)

    matrices = {
        "AG_ABS": matrix_from_edge_signs(ap, aq, aw, n, abs_sign),
        "AG_SIGNED": matrix_from_edge_signs(ap, aq, aw, n, bio_sign),
        "AG_SIGN_SHUFFLE": matrix_from_edge_signs(ap, aq, aw, n, shuffled_sign),
    }
    details = {
        "ach_gaba_edges": int(ap.size),
        "ach_source_nodes": int(np.sum(source_class == 1)),
        "gaba_source_nodes": int(np.sum(source_class == -1)),
        "excluded_source_nodes": int(np.sum(source_class == 0)),
    }
    return matrices, details


def evaluate_matrix(W, delay: int, seed: int):
    rng = np.random.default_rng(seed + 101)
    Win = rng.normal(0.0, 0.55, size=(W.shape[0], mem.EVENT_DIM)).astype(np.float32)

    train_seq, train_y = sweep.delayed_order_dataset(seed + 201, 40, delay)
    test_seq, test_y = sweep.delayed_order_dataset(seed + 1201, 20, delay)

    train_x = mem.reservoir_features(train_seq, W, Win)
    test_x = mem.reservoir_features(test_seq, W, Win)
    readout = mem.ridge_readout(train_x, train_y, 4)
    pred = mem.predict(readout, test_x)
    return {
        "accuracy": float(np.mean(pred == test_y)),
        "macro_f1": mem.macro_f1(test_y, pred, 4),
    }


def full_unsigned_r3(pre, post, weights, n, seed):
    W, _ = mem.build_memory_matrix("R3", pre, post, weights, n, seed)
    return W


def exact_sign_test(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return 1.0
    tail = min(wins, losses)
    return min(1.0, 2.0 * sum(math.comb(n, k) for k in range(tail + 1)) / (2 ** n))


def paired_summary(a: list[float], b: list[float]):
    # Return A-B.
    diffs = np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)
    wins = int(np.sum(diffs > 1e-12))
    losses = int(np.sum(diffs < -1e-12))
    ties = int(diffs.size - wins - losses)
    return {
        "cells": int(diffs.size),
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "mean_difference": float(diffs.mean()),
        "median_difference": float(np.median(diffs)),
        "two_sided_exact_sign_test_p": exact_sign_test(wins, losses),
    }


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

    traced = base.read_traced_ids(args.annotations)
    old_count = base.NODE_COUNT
    base.NODE_COUNT = NODE_COUNT
    try:
        selected, traced_rows = base.select_top_degree_traced(args.graph, traced)
    finally:
        base.NODE_COUNT = old_count
    pre, post, weights = base.extract_subgraph(args.graph, selected)
    nts, nt_counts = read_consensus_nt(args.neurotransmitters, selected)

    modes = ("FULL_UNSIGNED_R3", "AG_ABS", "AG_SIGNED", "AG_SIGN_SHUFFLE")
    cells = {mode: [] for mode in modes}
    per_delay = {}

    first_details = None
    for delay in DELAYS:
        per_delay[str(delay)] = {mode: [] for mode in modes}
        for seed in SEEDS:
            ag_matrices, details = build_ag_matrices(pre, post, weights, nts, selected.size, seed)
            if first_details is None:
                first_details = details

            matrices = {
                "FULL_UNSIGNED_R3": full_unsigned_r3(pre, post, weights, selected.size, seed),
                **ag_matrices,
            }
            for mode, W in matrices.items():
                result = evaluate_matrix(W, delay, seed)
                per_delay[str(delay)][mode].append(result)
                cells[mode].append(result["macro_f1"])

    aggregate = {
        mode: {
            "mean_macro_f1": float(np.mean(cells[mode])),
            "min_macro_f1": float(np.min(cells[mode])),
            "max_macro_f1": float(np.max(cells[mode])),
        }
        for mode in modes
    }

    delay_summary = {}
    for delay in DELAYS:
        key = str(delay)
        delay_summary[key] = {}
        for mode in modes:
            vals = [r["macro_f1"] for r in per_delay[key][mode]]
            delay_summary[key][mode] = {
                "mean_macro_f1": float(np.mean(vals)),
                "mean_accuracy": float(np.mean([r["accuracy"] for r in per_delay[key][mode]])),
            }

    output = {
        "schema": "panam.public.flycore.conservative_signed_nt.v1",
        "scope": "EXPLORATORY_SIGNED_NEUROTRANSMITTER_CHILD_NOT_PRODUCTION",
        "dataset": "MaleCNS v1.0",
        "selected_nodes": int(selected.size),
        "selected_edges": int(pre.size),
        "selected_body_id_sha256": hashlib.sha256(selected.tobytes()).hexdigest(),
        "traced_to_traced_edge_rows": int(traced_rows[0]),
        "selected_consensus_nt_counts": nt_counts,
        "sign_policy": {
            "acetylcholine": 1,
            "gaba": -1,
            "all_other_transmitters": "EXCLUDED_FROM_AG_SIGNED_CORE",
            "reason": "avoid imposing a universal binary sign on receptor/circuit-dependent or modulatory transmitter effects",
        },
        "ag_edge_mask": first_details,
        "seeds": list(SEEDS),
        "delays": list(DELAYS),
        "task": "delayed_order_4class",
        "per_delay": delay_summary,
        "aggregate": aggregate,
        "paired_ag_signed_minus_ag_abs": paired_summary(cells["AG_SIGNED"], cells["AG_ABS"]),
        "paired_ag_signed_minus_sign_shuffle": paired_summary(cells["AG_SIGNED"], cells["AG_SIGN_SHUFFLE"]),
        "paired_full_unsigned_minus_ag_abs": paired_summary(cells["FULL_UNSIGNED_R3"], cells["AG_ABS"]),
        "private_panam_data_used": False,
        "production_readiness_claimed": False,
        "promotion_decision": "NOT_MADE",
        "limitations": [
            "sign model is intentionally incomplete and only covers acetylcholine/GABA",
            "neurotransmitter identity alone does not encode postsynaptic receptor state",
            "single high-degree 192-neuron subgraph",
            "synthetic task family",
            "seed/delay cells share one biological graph",
        ],
    }

    print(json.dumps(output, sort_keys=True))
    print("PANAM_PUBLIC_FLYCORE_CONSERVATIVE_SIGNED_NT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

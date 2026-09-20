#!/usr/bin/env python3
"""Focused R2-vs-R3 biological weight-placement replication.

Refined hypothesis:
Does the observed R3 > R2 memory-capacity effect persist across multiple
deterministic subgraph sizes and two different selection rules?

R2 and R3 share the exact same MaleCNS topology and the same connection-weight
multiset. R2 permutes those weights across biological edges; R3 keeps the
published edge-to-weight assignment. Therefore this experiment isolates the
placement of connection strengths more directly than R0/R1 comparisons.

This is still an exploratory single-connectome experiment, not production
evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math

import numpy as np

import run_real_subgraph_canary as base
import run_delayed_memory_benchmark as mem
import run_linear_memory_capacity as mc
import run_unweighted_degree_memory_replication as unweighted

SIZES = (96, 144, 192)
SEEDS = (251, 257, 263, 269, 277, 281, 283, 293, 311, 313)


def weighted_degree_ranking(graph_path, traced):
    degree = np.zeros(traced.size, dtype=np.float64)
    traced_rows = 0
    for pre, post, weight in base.iter_graph_batches(graph_path):
        pi, pv = base.lookup_sorted(traced, pre)
        qi, qv = base.lookup_sorted(traced, post)
        mask = pv & qv
        if not np.any(mask):
            continue
        w = weight[mask].astype(np.float64, copy=False)
        np.add.at(degree, pi[mask], w)
        np.add.at(degree, qi[mask], w)
        traced_rows += int(mask.sum())
    order = np.lexsort((traced, -degree))
    return traced[order], degree[order], traced_rows


def unweighted_degree_ranking(graph_path, traced):
    degree = np.zeros(traced.size, dtype=np.int64)
    traced_rows = 0
    for pre, post, _weight in base.iter_graph_batches(graph_path):
        pi, pv = base.lookup_sorted(traced, pre)
        qi, qv = base.lookup_sorted(traced, post)
        mask = pv & qv
        if not np.any(mask):
            continue
        np.add.at(degree, pi[mask], 1)
        np.add.at(degree, qi[mask], 1)
        traced_rows += int(mask.sum())
    order = np.lexsort((traced, -degree))
    return traced[order], degree[order], traced_rows


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


def paired(r3, r2):
    d = np.asarray(r3, dtype=np.float64) - np.asarray(r2, dtype=np.float64)
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
        "bootstrap_95pct_mean_ci": bootstrap_ci(d),
        "two_sided_exact_sign_test_p": exact_sign_test(wins, losses),
        "relative_mean_difference_vs_r2": float(
            (np.mean(r3) - np.mean(r2)) / np.mean(r2)
        ) if np.mean(r2) > 0 else None,
    }


def evaluate_selection(graph_path, ranked_ids, ranked_score, rule):
    out = {}
    for size in SIZES:
        selected = np.sort(ranked_ids[:size])
        pre, post, weights = base.extract_subgraph(graph_path, selected)
        if pre.size < size:
            raise RuntimeError(f"subgraph_too_sparse:{rule}:{size}:{pre.size}")

        runs = {"R2": [], "R3": []}
        for variant in ("R2", "R3"):
            for seed in SEEDS:
                W, _ = mem.build_memory_matrix(
                    variant,
                    pre,
                    post,
                    weights,
                    selected.size,
                    seed,
                )
                raw = mc.evaluate_variant(W, seed)
                runs[variant].append(
                    {
                        "seed": seed,
                        "memory_capacity_1_60": raw["memory_capacity_1_60"],
                        "mc_1_10": raw["mc_1_10"],
                        "mc_11_30": raw["mc_11_30"],
                        "mc_31_60": raw["mc_31_60"],
                    }
                )

        total_r2 = [x["memory_capacity_1_60"] for x in runs["R2"]]
        total_r3 = [x["memory_capacity_1_60"] for x in runs["R3"]]
        long_r2 = [x["mc_31_60"] for x in runs["R2"]]
        long_r3 = [x["mc_31_60"] for x in runs["R3"]]

        out[str(size)] = {
            "selected_nodes": size,
            "selected_edges": int(pre.size),
            "selected_contact_weight_sum": float(weights.sum()),
            "selected_body_id_sha256": hashlib.sha256(selected.tobytes()).hexdigest(),
            "selection_score_min_at_cutoff": float(ranked_score[size - 1]),
            "variants": {
                variant: {
                    "runs": runs[variant],
                    "mean_memory_capacity_1_60": float(
                        np.mean([x["memory_capacity_1_60"] for x in runs[variant]])
                    ),
                    "mean_mc_31_60": float(
                        np.mean([x["mc_31_60"] for x in runs[variant]])
                    ),
                }
                for variant in ("R2", "R3")
            },
            "paired_r3_minus_r2_total_mc": paired(total_r3, total_r2),
            "paired_r3_minus_r2_long_mc_31_60": paired(long_r3, long_r2),
        }
    return out


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
    wrank, wscore, traced_rows_w = weighted_degree_ranking(args.graph, traced)
    urank, uscore, traced_rows_u = unweighted_degree_ranking(args.graph, traced)
    if traced_rows_w != traced_rows_u:
        raise RuntimeError("traced_edge_row_count_disagreement")

    selections = {
        "weighted_degree": evaluate_selection(args.graph, wrank, wscore, "weighted_degree"),
        "unweighted_degree": evaluate_selection(args.graph, urank, uscore, "unweighted_degree"),
    }

    all_total_r3 = []
    all_total_r2 = []
    all_long_r3 = []
    all_long_r2 = []
    cell_wins_total = 0
    cell_losses_total = 0
    cell_wins_long = 0
    cell_losses_long = 0

    for rule in selections.values():
        for size_result in rule.values():
            for r in size_result["variants"]["R3"]["runs"]:
                all_total_r3.append(r["memory_capacity_1_60"])
                all_long_r3.append(r["mc_31_60"])
            for r in size_result["variants"]["R2"]["runs"]:
                all_total_r2.append(r["memory_capacity_1_60"])
                all_long_r2.append(r["mc_31_60"])
            ptotal = size_result["paired_r3_minus_r2_total_mc"]
            plong = size_result["paired_r3_minus_r2_long_mc_31_60"]
            cell_wins_total += ptotal["wins"]
            cell_losses_total += ptotal["losses"]
            cell_wins_long += plong["wins"]
            cell_losses_long += plong["losses"]

    output = {
        "schema": "panam.public.flycore.weight_placement_multiscale_replication.v1",
        "scope": "REFINED_R2_R3_HYPOTHESIS_EXPERIMENT_NOT_PRODUCTION",
        "dataset": "MaleCNS v1.0",
        "hypothesis": "published biological placement of connection strengths carries recurrent memory structure beyond the same topology with the same weights permuted across edges",
        "sizes": list(SIZES),
        "seeds": list(SEEDS),
        "seed_overlap_with_prior_memory_experiments": [],
        "selection_rules": [
            "weighted incident contact-count degree",
            "unweighted incident traced-to-traced connection-row degree",
        ],
        "contract": {
            "max_lag": mc.MAX_LAG,
            "washout": mc.WASHOUT,
            "train_steps": mc.TRAIN_STEPS,
            "test_steps": mc.TEST_STEPS,
            "leak": mc.LEAK,
            "recurrent_abs_row_sum_target": mem.MEMORY_ROW_SUM,
            "input_scale": mc.INPUT_SCALE,
            "ridge": mc.RIDGE,
        },
        "traced_to_traced_edge_rows": int(traced_rows_w),
        "selections": selections,
        "pooled_descriptive": {
            "paired_r3_minus_r2_total_mc": paired(all_total_r3, all_total_r2),
            "paired_r3_minus_r2_long_mc_31_60": paired(all_long_r3, all_long_r2),
            "note": "pooled cells share one biological connectome and are not independent biological replicates",
        },
        "private_panam_data_used": False,
        "production_readiness_claimed": False,
        "promotion_decision": "NOT_MADE",
        "limitations": [
            "single MaleCNS connectome",
            "two deterministic high-degree selection families only",
            "sizes are nested within each selection rule",
            "stochastic seeds are not independent biological samples",
            "lag measured only through 60",
            "fixed reservoir operating point",
            "R3 uses unsigned contact-count strengths",
        ],
    }

    print(json.dumps(output, sort_keys=True))
    print("PANAM_PUBLIC_FLYCORE_WEIGHT_PLACEMENT_MULTISCALE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

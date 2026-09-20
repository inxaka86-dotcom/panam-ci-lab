#!/usr/bin/env python3
"""Preregistered FlyCore low-data / rapid-adaptation benchmark.

Architectures and recurrent operating points are frozen from the preceding
strong-baseline round. This child round changes only the number of labelled
training targets available to each model.

R3 and sparse ESN keep their recurrent cores frozen and train only a ridge
readout. GRU trains all recurrent parameters from the same labelled examples.

Public MaleCNS + deterministic synthetic NARMA only. No PANAM private data.
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np

import run_strong_baseline_narma as strong

BUDGETS = (32, 64, 128, 256, 512, 2500)
CONSTRAINED_BUDGETS = BUDGETS[:-1]
TEST_SEEDS = (601, 607, 613, 617, 619)

FROZEN = {
    10: {
        "R3": {"gain": 1.15, "input_scale": 0.55, "leak": 0.50},
        "SPARSE_ESN": {"gain": 1.15, "input_scale": 0.80, "leak": 0.30},
        "GRU": {"hidden_units": 64, "learning_rate": 0.003, "epochs": 59},
    },
    20: {
        "R3": {"gain": 1.15, "input_scale": 0.80, "leak": 0.30},
        "SPARSE_ESN": {"gain": 1.15, "input_scale": 0.80, "leak": 0.15},
        "GRU": {"hidden_units": 64, "learning_rate": 0.003, "epochs": 49},
    },
}


def reservoir_budget_runs(model, cfg, pre, post, weights, order, seed):
    u, target, data_seed = strong.generate_narma(
        order, seed, strong.TEST_STEPS, return_data_seed=True
    )

    rng = np.random.default_rng(seed + 17_003)
    win_base = rng.normal(0.0, 1.0, size=strong.NODE_COUNT)
    win = win_base * cfg["input_scale"]

    if model == "R3":
        W = strong.build_r3(
            pre, post, weights, strong.NODE_COUNT, cfg["gain"]
        )
    elif model == "SPARSE_ESN":
        W = strong.build_sparse_esn(
            strong.NODE_COUNT, len(pre), cfg["gain"], seed
        )
    else:
        raise ValueError(model)

    states, state_seconds = strong.drive_sparse(W, u, win, cfg["leak"])

    test_start = strong.WASHOUT + strong.TRAIN_STEPS
    test_end = test_start + strong.TEST_STEPS

    out = []
    for budget in BUDGETS:
        train_start = strong.WASHOUT
        train_end = train_start + budget

        t0 = time.perf_counter()
        readout = strong.ridge_fit(states, target, train_start, train_end)
        train_seconds = time.perf_counter() - t0

        pred = strong.ridge_predict(readout, states, test_start, test_end)
        score = strong.nmse(target[test_start:test_end], pred)

        out.append({
            "requested_seed": int(seed),
            "data_seed": int(data_seed),
            "budget": int(budget),
            "nmse": float(score),
            "train_seconds": float(train_seconds),
            "state_update_microseconds_per_step": float(
                state_seconds / u.size * 1e6
            ),
            "recurrent_nonzeros": int(W.nnz),
            "model_bytes": strong.sparse_model_bytes(W, win, readout),
        })
    return out


def train_test_gru_budget(order: int, seed: int, budget: int, cfg):
    torch = strong._torch()
    torch.manual_seed(seed + 97_003)

    u, target, data_seed = strong.generate_narma(
        order, seed, strong.TEST_STEPS, return_data_seed=True
    )

    train_start = strong.WASHOUT
    train_end = train_start + budget
    test_start = strong.WASHOUT + strong.TRAIN_STEPS
    test_end = test_start + strong.TEST_STEPS

    Xtr, Ytr = strong.make_windows(u, target, train_start, train_end)
    Xte, Yte = strong.make_windows(u, target, test_start, test_end)

    input_max = 0.5 if order == 10 else 0.2
    x_mean, x_scale = input_max / 2.0, input_max / 2.0
    y_mean = float(np.mean(Ytr))
    y_std = float(np.std(Ytr))
    if not np.isfinite(y_std) or y_std <= 0:
        raise RuntimeError("invalid_gru_training_target_std")

    Xtr = ((Xtr - x_mean) / x_scale)[:, :, None]
    Xte = ((Xte - x_mean) / x_scale)[:, :, None]
    Ytrn = (Ytr - y_mean) / y_std

    tx = torch.from_numpy(Xtr)
    ty = torch.from_numpy(Ytrn)
    vx = torch.from_numpy(Xte)

    model = strong.GRUNetFactory.make(cfg["hidden_units"])
    opt = torch.optim.Adam(model.parameters(), lr=cfg["learning_rate"])
    loss_fn = torch.nn.MSELoss()
    generator = torch.Generator().manual_seed(seed + 98_003)

    t0 = time.perf_counter()
    for _epoch in range(cfg["epochs"]):
        model.train()
        perm = torch.randperm(tx.shape[0], generator=generator)
        for begin in range(0, tx.shape[0], strong.GRU_BATCH):
            idx = perm[begin:begin + strong.GRU_BATCH]
            opt.zero_grad(set_to_none=True)
            pred = model(tx[idx])
            loss = loss_fn(pred, ty[idx])
            loss.backward()
            opt.step()
    train_seconds = time.perf_counter() - t0

    model.eval()
    with torch.no_grad():
        _ = model(vx[: min(32, vx.shape[0])])
        t1 = time.perf_counter()
        pred = model(vx)
        infer_seconds = time.perf_counter() - t1
        pred = pred.cpu().numpy() * y_std + y_mean

    params = int(sum(p.numel() for p in model.parameters()))
    model_bytes = int(
        sum(p.numel() * p.element_size() for p in model.parameters())
    )

    return {
        "requested_seed": int(seed),
        "data_seed": int(data_seed),
        "budget": int(budget),
        "nmse": strong.nmse(
            Yte.astype(np.float64), pred.astype(np.float64)
        ),
        "train_seconds": float(train_seconds),
        "inference_microseconds_per_window": float(
            infer_seconds / Xte.shape[0] * 1e6
        ),
        "parameter_count": params,
        "model_bytes": model_bytes,
    }


def aggregate_budget(runs, budget):
    xs = [x for x in runs if x["budget"] == budget]
    return {
        "mean_nmse": float(np.mean([x["nmse"] for x in xs])),
        "median_nmse": float(np.median([x["nmse"] for x in xs])),
        "mean_train_seconds": float(np.mean([x["train_seconds"] for x in xs])),
        "seed_nmse": {
            str(x["requested_seed"]): float(x["nmse"]) for x in xs
        },
    }


def paired_summary(a_runs, b_runs, budget):
    a = {
        x["requested_seed"]: x["nmse"]
        for x in a_runs if x["budget"] == budget
    }
    b = {
        x["requested_seed"]: x["nmse"]
        for x in b_runs if x["budget"] == budget
    }
    seeds = sorted(set(a) & set(b))
    diffs = np.asarray([a[s] - b[s] for s in seeds], dtype=np.float64)
    wins = int(np.sum(diffs < -1e-12))
    losses = int(np.sum(diffs > 1e-12))
    ties = int(diffs.size - wins - losses)
    mean_a = float(np.mean([a[s] for s in seeds]))
    mean_b = float(np.mean([b[s] for s in seeds]))
    return {
        "cells": len(seeds),
        "a_wins": wins,
        "a_losses": losses,
        "ties": ties,
        "mean_a_minus_b_nmse": float(np.mean(diffs)),
        "relative_nmse_change_a_vs_b": (
            float((mean_a - mean_b) / mean_b) if mean_b > 0 else None
        ),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--order", required=True, type=int, choices=(10, 20))
    p.add_argument("--graph", required=True, type=strong.base.Path)
    p.add_argument("--annotations", required=True, type=strong.base.Path)
    args = p.parse_args()

    strong.base.require_artifact(
        args.graph,
        strong.base.GRAPH_NAME,
        strong.base.GRAPH_BYTES,
        strong.base.GRAPH_SHA256,
    )
    strong.base.require_artifact(
        args.annotations,
        strong.base.ANNOTATION_NAME,
        strong.base.ANNOTATION_BYTES,
        strong.base.ANNOTATION_SHA256,
    )

    traced = strong.base.read_traced_ids(args.annotations)
    old = strong.base.NODE_COUNT
    strong.base.NODE_COUNT = strong.NODE_COUNT
    try:
        selected, traced_rows = strong.base.select_top_degree_traced(
            args.graph, traced
        )
    finally:
        strong.base.NODE_COUNT = old

    pre, post, weights = strong.base.extract_subgraph(args.graph, selected)
    cfg = FROZEN[args.order]

    all_runs = {"R3": [], "SPARSE_ESN": [], "GRU": []}

    for seed in TEST_SEEDS:
        all_runs["R3"].extend(
            reservoir_budget_runs(
                "R3", cfg["R3"], pre, post, weights, args.order, seed
            )
        )
        all_runs["SPARSE_ESN"].extend(
            reservoir_budget_runs(
                "SPARSE_ESN",
                cfg["SPARSE_ESN"],
                pre,
                post,
                weights,
                args.order,
                seed,
            )
        )
        for budget in BUDGETS:
            all_runs["GRU"].append(
                train_test_gru_budget(
                    args.order, seed, budget, cfg["GRU"]
                )
            )

    aggregate = {
        model: {
            str(budget): aggregate_budget(runs, budget)
            for budget in BUDGETS
        }
        for model, runs in all_runs.items()
    }

    comparisons = {
        "R3_vs_SPARSE_ESN": {
            str(b): paired_summary(
                all_runs["R3"], all_runs["SPARSE_ESN"], b
            )
            for b in BUDGETS
        },
        "R3_vs_GRU": {
            str(b): paired_summary(all_runs["R3"], all_runs["GRU"], b)
            for b in BUDGETS
        },
    }

    r3_esn_better = 0
    meaningful = False
    r3_gru_competitive = False
    constrained_cost_ratios = {}

    for budget in CONSTRAINED_BUDGETS:
        key = str(budget)
        r3_nmse = aggregate["R3"][key]["mean_nmse"]
        esn_nmse = aggregate["SPARSE_ESN"][key]["mean_nmse"]
        gru_nmse = aggregate["GRU"][key]["mean_nmse"]

        if r3_nmse < esn_nmse:
            r3_esn_better += 1
        if esn_nmse > 0 and (esn_nmse - r3_nmse) / esn_nmse >= 0.05:
            meaningful = True
        if r3_nmse <= 1.25 * gru_nmse:
            r3_gru_competitive = True

        gru_train = aggregate["GRU"][key]["mean_train_seconds"]
        r3_train = aggregate["R3"][key]["mean_train_seconds"]
        constrained_cost_ratios[key] = (
            float(r3_train / gru_train) if gru_train > 0 else None
        )

    output = {
        "schema": "panam.public.flycore.low_data_adaptation.v1",
        "scope": "PREREGISTERED_PUBLIC_SYNTHETIC_LOW_DATA_NOT_PRODUCTION",
        "dataset": "MaleCNS v1.0",
        "task": f"NARMA{args.order}",
        "metric": "NMSE lower is better",
        "selected_nodes": int(selected.size),
        "selected_edges": int(pre.size),
        "selected_body_id_sha256": strong.base.hashlib.sha256(
            selected.tobytes()
        ).hexdigest(),
        "traced_to_traced_edge_rows": int(traced_rows[0]),
        "budgets": list(BUDGETS),
        "constrained_budgets": list(CONSTRAINED_BUDGETS),
        "test_seeds": list(TEST_SEEDS),
        "frozen_configs": cfg,
        "data_seed_resolution": {
            str(seed): int(
                strong.generate_narma(
                    args.order,
                    seed,
                    strong.TEST_STEPS,
                    return_data_seed=True,
                )[2]
            )
            for seed in TEST_SEEDS
        },
        "fairness": {
            "no_hyperparameter_search_in_this_round": True,
            "same_labelled_target_count_within_budget": True,
            "same_generated_series_within_seed": True,
            "same_test_tail_within_seed": True,
            "reservoir_recurrent_cores_frozen": True,
            "GRU_recurrent_core_trained": True,
        },
        "aggregate": aggregate,
        "comparisons": comparisons,
        "decision_components": {
            "R3_lower_mean_NMSE_than_ESN_constrained_budget_count": r3_esn_better,
            "required_count": 4,
            "low_data_advantage_vs_sparse_esn": r3_esn_better >= 4,
            "R3_relative_ESN_improvement_at_least_5pct_any_constrained_budget": meaningful,
            "R3_within_25pct_of_GRU_any_constrained_budget": r3_gru_competitive,
            "R3_readout_fit_to_GRU_train_time_ratio_by_budget": constrained_cost_ratios,
        },
        "runs": all_runs,
        "private_panam_data_used": False,
        "production_readiness_claimed": False,
        "promotion_decision": "NOT_MADE_BY_SINGLE_TASK",
        "limitations": [
            "single MaleCNS connectome and one 192-node weighted-degree subgraph",
            "synthetic NARMA tasks only",
            "architectures frozen from prior strong-baseline round",
            "reservoirs receive unlabeled input during the gap before the frozen test tail while labels are budget-limited",
            "GRU uses fixed epochs, so optimizer-step count decreases with smaller labelled datasets",
            "GitHub-hosted CPU timing is descriptive and not a portable production benchmark",
        ],
    }

    print(json.dumps(output, sort_keys=True, allow_nan=False))
    print(
        f"PANAM_PUBLIC_FLYCORE_LOW_DATA_NARMA{args.order}=PASS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

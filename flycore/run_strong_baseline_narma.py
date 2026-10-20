#!/usr/bin/env python3
"""Preregistered strong-baseline FlyCore benchmark for generalized NARMA.

Compares:
- R3 MaleCNS published topology + published edge-to-weight placement;
- a tuned conventional sparse ESN with the same node and edge count;
- a compact trained GRU.

All task data are deterministic synthetic series. No PANAM private data is used.
Model selection uses validation seeds only; test seeds are disjoint.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import time
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp

import run_real_subgraph_canary as base

NODE_COUNT = 192
WASHOUT = 250
TRAIN_STEPS = 2500
VALIDATION_STEPS = 1000
TEST_STEPS = 1500
VALIDATION_SEEDS = (503, 509, 521)
TEST_SEEDS = (541, 547, 557, 563, 569)
R3_GAINS = (0.50, 0.75, 0.95, 1.15)
R3_LEAKS = (0.15, 0.30, 0.50)
ESN_GAINS = R3_GAINS
ESN_LEAKS = R3_LEAKS
ESN_INPUT_SCALES = (0.30, 0.55, 0.80)
R3_INPUT_SCALES = ESN_INPUT_SCALES
RIDGE = 1e-6
GRU_HIDDEN = (32, 64)
GRU_LR = (0.001, 0.003)
GRU_WINDOW = 40
GRU_MAX_EPOCHS = 60
GRU_PATIENCE = 8
GRU_BATCH = 128


def _generate_narma_once(order: int, data_seed: int, eval_steps: int):
    total = WASHOUT + TRAIN_STEPS + eval_steps + 1
    rng = np.random.default_rng(data_seed)
    input_max = 0.5 if order == 10 else 0.2
    u = rng.uniform(0.0, input_max, size=total).astype(np.float64)
    y = np.zeros(total + 1, dtype=np.float64)

    with np.errstate(over="ignore", invalid="ignore"):
        for t in range(total):
            lo = max(0, t - order + 1)
            hist_sum = float(np.sum(y[lo:t + 1]))
            delayed_u = u[t - order + 1] if t - order + 1 >= 0 else 0.0
            y[t + 1] = (
                0.3 * y[t]
                + 0.05 * y[t] * hist_sum
                + 1.5 * delayed_u * u[t]
                + 0.1
            )
    return u, y[1:total + 1]


def generate_narma(order: int, seed: int, eval_steps: int, *, return_data_seed=False):
    for offset in range(100):
        data_seed = seed + offset
        u, target = _generate_narma_once(order, data_seed, eval_steps)
        stable = (
            np.all(np.isfinite(target))
            and np.all(np.isfinite(u))
            and float(np.max(np.abs(target))) <= 10.0
        )
        if stable:
            if return_data_seed:
                return u, target, data_seed
            return u, target
    raise RuntimeError(f"no_stable_narma_dataset_within_100_seeds:{seed}")


def nmse(target: np.ndarray, pred: np.ndarray) -> float:
    if not np.all(np.isfinite(target)) or not np.all(np.isfinite(pred)):
        raise RuntimeError("nonfinite_nmse_input")
    var = float(np.var(target))
    if var <= 0:
        raise RuntimeError("zero_target_variance")
    return float(np.mean((target - pred) ** 2) / var)


def scale_abs_row_sum(W: sp.csr_matrix, target: float) -> sp.csr_matrix:
    row = np.asarray(np.abs(W).sum(axis=1)).ravel()
    mx = float(np.max(row))
    if mx <= 0:
        raise RuntimeError("zero_recurrent_matrix")
    return (W * (target / mx)).tocsr()


def build_r3(pre, post, contact_weight, n, gain):
    data = np.log1p(contact_weight.astype(np.float64))
    W = sp.csr_matrix((data, (post, pre)), shape=(n, n), dtype=np.float64)
    W.sum_duplicates()
    return scale_abs_row_sum(W, gain)


def build_sparse_esn(n: int, edge_count: int, gain: float, seed: int):
    rng = np.random.default_rng(seed + 41_003)
    if edge_count > n * n:
        raise RuntimeError("edge_count_exceeds_dense_pair_space")
    codes = rng.choice(n * n, size=edge_count, replace=False)
    pre = codes // n
    post = codes % n
    data = rng.normal(0.0, 1.0, size=edge_count)
    W = sp.csr_matrix((data, (post, pre)), shape=(n, n), dtype=np.float64)
    W.sum_duplicates()
    return scale_abs_row_sum(W, gain)


def drive_sparse(
    W: sp.csr_matrix,
    u: np.ndarray,
    win: np.ndarray,
    leak: float,
):
    x = np.zeros(W.shape[0], dtype=np.float64)
    states = np.empty((u.size, W.shape[0]), dtype=np.float64)
    start = time.perf_counter()
    for t, val in enumerate(u):
        x = (1.0 - leak) * x + leak * np.tanh(W.dot(x) + win * val)
        states[t] = x
    elapsed = time.perf_counter() - start
    return states, elapsed


def ridge_fit(states, target, start, end):
    X = states[start:end]
    X = np.column_stack([np.ones(X.shape[0]), X])
    Y = target[start:end]
    reg = np.eye(X.shape[1], dtype=np.float64) * RIDGE
    reg[0, 0] = 0.0
    return np.linalg.solve(X.T @ X + reg, X.T @ Y)


def ridge_predict(readout, states, start, end):
    X = states[start:end]
    X = np.column_stack([np.ones(X.shape[0]), X])
    return X @ readout


def sparse_model_bytes(W: sp.csr_matrix, win: np.ndarray, readout: np.ndarray):
    return int(
        W.data.nbytes
        + W.indices.nbytes
        + W.indptr.nbytes
        + win.nbytes
        + readout.nbytes
    )


def evaluate_reservoir(
    model: str,
    pre,
    post,
    weights,
    order: int,
    seed: int,
    eval_steps: int,
    gain: float,
    leak: float,
    input_scale: float,
):
    u, target = generate_narma(order, seed, eval_steps)
    rng = np.random.default_rng(seed + 17_003)
    win_base = rng.normal(0.0, 1.0, size=NODE_COUNT)
    win = win_base * input_scale

    if model == "R3":
        W = build_r3(pre, post, weights, NODE_COUNT, gain)
    elif model == "SPARSE_ESN":
        W = build_sparse_esn(NODE_COUNT, len(pre), gain, seed)
    else:
        raise ValueError(model)

    states, elapsed = drive_sparse(W, u, win, leak)
    train_start = WASHOUT
    train_end = WASHOUT + TRAIN_STEPS
    eval_start = train_end
    eval_end = train_end + eval_steps

    fit_start = time.perf_counter()
    readout = ridge_fit(states, target, train_start, train_end)
    readout_seconds = time.perf_counter() - fit_start
    pred = ridge_predict(readout, states, eval_start, eval_end)
    score = nmse(target[eval_start:eval_end], pred)

    return {
        "nmse": score,
        "state_update_microseconds_per_step": float(elapsed / u.size * 1e6),
        "train_readout_seconds": float(readout_seconds),
        "recurrent_nonzeros": int(W.nnz),
        "model_bytes": sparse_model_bytes(W, win, readout),
    }


def tune_reservoir(model, pre, post, weights, order):
    if model == "R3":
        configs = [
            {"gain": g, "leak": l, "input_scale": s}
            for g in R3_GAINS
            for l in R3_LEAKS
            for s in R3_INPUT_SCALES
        ]
    else:
        configs = [
            {"gain": g, "leak": l, "input_scale": s}
            for g in ESN_GAINS
            for l in ESN_LEAKS
            for s in ESN_INPUT_SCALES
        ]

    rows = []
    for cfg in configs:
        vals = []
        for seed in VALIDATION_SEEDS:
            vals.append(
                evaluate_reservoir(
                    model,
                    pre,
                    post,
                    weights,
                    order,
                    seed,
                    VALIDATION_STEPS,
                    cfg["gain"],
                    cfg["leak"],
                    cfg["input_scale"],
                )["nmse"]
            )
        rows.append({
            **cfg,
            "validation_mean_nmse": float(np.mean(vals)),
            "validation_max_nmse": float(np.max(vals)),
            "validation_seed_nmse": vals,
        })

    rows.sort(key=lambda x: (
        x["validation_mean_nmse"],
        x["validation_max_nmse"],
        x["gain"],
        x["leak"],
        x["input_scale"],
    ))
    return rows[0], rows


def test_reservoir(model, cfg, pre, post, weights, order):
    runs = []
    for seed in TEST_SEEDS:
        runs.append({
            "seed": seed,
            **evaluate_reservoir(
                model,
                pre,
                post,
                weights,
                order,
                seed,
                TEST_STEPS,
                cfg["gain"],
                cfg["leak"],
                cfg["input_scale"],
            ),
        })
    return {
        "runs": runs,
        "mean_nmse": float(np.mean([x["nmse"] for x in runs])),
        "median_nmse": float(np.median([x["nmse"] for x in runs])),
        "mean_state_update_microseconds_per_step": float(
            np.mean([x["state_update_microseconds_per_step"] for x in runs])
        ),
        "mean_model_bytes": float(np.mean([x["model_bytes"] for x in runs])),
    }


def _torch():
    import torch
    torch.set_num_threads(2)
    return torch


class GRUNetFactory:
    @staticmethod
    def make(hidden: int):
        torch = _torch()
        class Model(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.gru = torch.nn.GRU(
                    input_size=1,
                    hidden_size=hidden,
                    num_layers=1,
                    batch_first=True,
                )
                self.out = torch.nn.Linear(hidden, 1)

            def forward(self, x):
                z, _ = self.gru(x)
                return self.out(z[:, -1, :]).squeeze(-1)
        return Model()


def make_windows(u, target, start, end):
    X, Y = [], []
    for t in range(start, end):
        lo = t - GRU_WINDOW + 1
        if lo < 0:
            continue
        X.append(u[lo:t + 1])
        Y.append(target[t])
    return np.asarray(X, dtype=np.float32), np.asarray(Y, dtype=np.float32)


def train_gru_validation(order: int, seed: int, hidden: int, lr: float):
    torch = _torch()
    torch.manual_seed(seed + 77_003)
    u, target = generate_narma(order, seed, VALIDATION_STEPS)

    train_start = WASHOUT
    train_end = WASHOUT + TRAIN_STEPS
    val_start = train_end
    val_end = train_end + VALIDATION_STEPS

    Xtr, Ytr = make_windows(u, target, train_start, train_end)
    Xva, Yva = make_windows(u, target, val_start, val_end)

    input_max = 0.5 if order == 10 else 0.2
    x_mean, x_scale = input_max / 2.0, input_max / 2.0
    y_mean = float(np.mean(Ytr))
    y_std = float(np.std(Ytr))
    if y_std <= 0:
        raise RuntimeError("zero_gru_target_std")

    Xtr = ((Xtr - x_mean) / x_scale)[:, :, None]
    Xva = ((Xva - x_mean) / x_scale)[:, :, None]
    Ytrn = (Ytr - y_mean) / y_std

    tx = torch.from_numpy(Xtr)
    ty = torch.from_numpy(Ytrn)
    vx = torch.from_numpy(Xva)

    model = GRUNetFactory.make(hidden)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = torch.nn.MSELoss()
    generator = torch.Generator().manual_seed(seed + 88_003)

    best_nmse = float("inf")
    best_epoch = 0
    best_state = None
    patience = 0
    train_start_time = time.perf_counter()

    for epoch in range(1, GRU_MAX_EPOCHS + 1):
        model.train()
        perm = torch.randperm(tx.shape[0], generator=generator)
        for begin in range(0, tx.shape[0], GRU_BATCH):
            idx = perm[begin:begin + GRU_BATCH]
            opt.zero_grad(set_to_none=True)
            pred = model(tx[idx])
            loss = loss_fn(pred, ty[idx])
            loss.backward()
            opt.step()

        model.eval()
        with torch.no_grad():
            pred = model(vx).cpu().numpy() * y_std + y_mean
        score = nmse(Yva.astype(np.float64), pred.astype(np.float64))
        if score < best_nmse - 1e-8:
            best_nmse = score
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
            patience = 0
        else:
            patience += 1
            if patience >= GRU_PATIENCE:
                break

    elapsed = time.perf_counter() - train_start_time
    return {
        "validation_nmse": float(best_nmse),
        "best_epoch": int(best_epoch),
        "epochs_ran": int(epoch),
        "train_seconds": float(elapsed),
        "best_state_available": best_state is not None,
    }


def tune_gru(order: int):
    configs = []
    for hidden in GRU_HIDDEN:
        for lr in GRU_LR:
            runs = [
                train_gru_validation(order, seed, hidden, lr)
                for seed in VALIDATION_SEEDS
            ]
            configs.append({
                "hidden_units": hidden,
                "learning_rate": lr,
                "validation_mean_nmse": float(
                    np.mean([x["validation_nmse"] for x in runs])
                ),
                "validation_max_nmse": float(
                    np.max([x["validation_nmse"] for x in runs])
                ),
                "validation_runs": runs,
                "selected_epochs_if_chosen": int(
                    round(np.median([x["best_epoch"] for x in runs]))
                ),
            })

    configs.sort(key=lambda x: (
        x["validation_mean_nmse"],
        x["validation_max_nmse"],
        x["hidden_units"],
        x["learning_rate"],
    ))
    chosen = configs[0]
    chosen["selected_epochs_if_chosen"] = max(
        1, chosen["selected_epochs_if_chosen"]
    )
    return chosen, configs


def train_test_gru(order: int, seed: int, hidden: int, lr: float, epochs: int):
    torch = _torch()
    torch.manual_seed(seed + 97_003)
    u, target = generate_narma(order, seed, TEST_STEPS)

    train_start = WASHOUT
    train_end = WASHOUT + TRAIN_STEPS
    test_start = train_end
    test_end = train_end + TEST_STEPS

    Xtr, Ytr = make_windows(u, target, train_start, train_end)
    Xte, Yte = make_windows(u, target, test_start, test_end)

    y_mean = float(np.mean(Ytr))
    y_std = float(np.std(Ytr))
    input_max = 0.5 if order == 10 else 0.2
    x_mean, x_scale = input_max / 2.0, input_max / 2.0
    Xtr = ((Xtr - x_mean) / x_scale)[:, :, None]
    Xte = ((Xte - x_mean) / x_scale)[:, :, None]
    Ytrn = (Ytr - y_mean) / y_std

    tx = torch.from_numpy(Xtr)
    ty = torch.from_numpy(Ytrn)
    vx = torch.from_numpy(Xte)

    model = GRUNetFactory.make(hidden)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = torch.nn.MSELoss()
    generator = torch.Generator().manual_seed(seed + 98_003)

    start = time.perf_counter()
    for _epoch in range(epochs):
        model.train()
        perm = torch.randperm(tx.shape[0], generator=generator)
        for begin in range(0, tx.shape[0], GRU_BATCH):
            idx = perm[begin:begin + GRU_BATCH]
            opt.zero_grad(set_to_none=True)
            pred = model(tx[idx])
            loss = loss_fn(pred, ty[idx])
            loss.backward()
            opt.step()
    train_seconds = time.perf_counter() - start

    model.eval()
    with torch.no_grad():
        # Warm one call before timing.
        _ = model(vx[: min(32, vx.shape[0])])
        t0 = time.perf_counter()
        pred = model(vx)
        infer_seconds = time.perf_counter() - t0
        pred = pred.cpu().numpy() * y_std + y_mean

    params = int(sum(p.numel() for p in model.parameters()))
    model_bytes = int(sum(p.numel() * p.element_size() for p in model.parameters()))

    return {
        "seed": seed,
        "nmse": nmse(Yte.astype(np.float64), pred.astype(np.float64)),
        "train_seconds": float(train_seconds),
        "inference_microseconds_per_window": float(
            infer_seconds / Xte.shape[0] * 1e6
        ),
        "parameter_count": params,
        "model_bytes": model_bytes,
    }


def test_gru(order: int, cfg):
    runs = [
        train_test_gru(
            order,
            seed,
            cfg["hidden_units"],
            cfg["learning_rate"],
            cfg["selected_epochs_if_chosen"],
        )
        for seed in TEST_SEEDS
    ]
    return {
        "runs": runs,
        "mean_nmse": float(np.mean([x["nmse"] for x in runs])),
        "median_nmse": float(np.median([x["nmse"] for x in runs])),
        "mean_train_seconds": float(np.mean([x["train_seconds"] for x in runs])),
        "mean_inference_microseconds_per_window": float(
            np.mean([x["inference_microseconds_per_window"] for x in runs])
        ),
        "parameter_count": int(runs[0]["parameter_count"]),
        "model_bytes": int(runs[0]["model_bytes"]),
    }


def paired_lower_is_better(a, b):
    # a-b; negative favors a.
    d = np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)
    wins = int(np.sum(d < -1e-12))
    losses = int(np.sum(d > 1e-12))
    ties = int(d.size - wins - losses)
    n = wins + losses
    p = 1.0 if n == 0 else min(
        1.0,
        2.0 * sum(math.comb(n, k) for k in range(min(wins, losses) + 1))
        / (2 ** n),
    )
    return {
        "cells": int(d.size),
        "a_wins": wins,
        "a_losses": losses,
        "ties": ties,
        "mean_a_minus_b_nmse": float(np.mean(d)),
        "median_a_minus_b_nmse": float(np.median(d)),
        "relative_nmse_change_a_vs_b": float(
            (np.mean(a) - np.mean(b)) / np.mean(b)
        ) if np.mean(b) > 0 else None,
        "two_sided_exact_sign_test_p": float(p),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--order", type=int, choices=(10, 20), required=True)
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

    r3_cfg, r3_grid = tune_reservoir("R3", pre, post, weights, args.order)
    esn_cfg, esn_grid = tune_reservoir(
        "SPARSE_ESN", pre, post, weights, args.order
    )
    gru_cfg, gru_grid = tune_gru(args.order)

    r3 = test_reservoir("R3", r3_cfg, pre, post, weights, args.order)
    esn = test_reservoir(
        "SPARSE_ESN", esn_cfg, pre, post, weights, args.order
    )
    gru = test_gru(args.order, gru_cfg)

    r3_nmse = [x["nmse"] for x in r3["runs"]]
    esn_nmse = [x["nmse"] for x in esn["runs"]]
    gru_nmse = [x["nmse"] for x in gru["runs"]]

    r3_vs_esn = paired_lower_is_better(r3_nmse, esn_nmse)
    r3_vs_gru = paired_lower_is_better(r3_nmse, gru_nmse)

    runtime_ratio = (
        r3["mean_state_update_microseconds_per_step"]
        / esn["mean_state_update_microseconds_per_step"]
        if esn["mean_state_update_microseconds_per_step"] > 0
        else None
    )

    output = {
        "schema": "panam.public.flycore.strong_baseline_narma.v1",
        "scope": "PREREGISTERED_PUBLIC_SYNTHETIC_STRONG_BASELINE_NOT_PRODUCTION",
        "dataset": "MaleCNS v1.0",
        "task": {
            "name": f"NARMA{args.order}",
            "order": args.order,
            "input_distribution": (
                "iid Uniform[0,0.5]" if args.order == 10
                else "iid Uniform[0,0.2]"
            ),
            "metric": "NMSE lower is better",
            "generator": "generalized NARMA-m recurrence",
        },
        "selected_nodes": int(selected.size),
        "selected_edges": int(pre.size),
        "selected_body_id_sha256": base.hashlib.sha256(selected.tobytes()).hexdigest(),
        "traced_to_traced_edge_rows": int(traced_rows[0]),
        "validation_seeds": list(VALIDATION_SEEDS),
        "test_seeds": list(TEST_SEEDS),
        "validation_test_seed_overlap": [],
        "data_seed_resolution": {
            "validation": {
                str(seed): generate_narma(
                    args.order, seed, VALIDATION_STEPS, return_data_seed=True
                )[2]
                for seed in VALIDATION_SEEDS
            },
            "test": {
                str(seed): generate_narma(
                    args.order, seed, TEST_STEPS, return_data_seed=True
                )[2]
                for seed in TEST_SEEDS
            },
            "stability_criterion": "all finite and max_abs_target <= 10",
        },
        "contract": {
            "washout": WASHOUT,
            "train_steps": TRAIN_STEPS,
            "validation_steps": VALIDATION_STEPS,
            "test_steps": TEST_STEPS,
            "ridge": RIDGE,
            "same_task_series_within_seed_for_all_models": True,
            "test_metrics_read_after_model_selection": True,
        },
        "chosen": {
            "R3": r3_cfg,
            "SPARSE_ESN": esn_cfg,
            "GRU": gru_cfg,
        },
        "validation_grids": {
            "R3": r3_grid,
            "SPARSE_ESN": esn_grid,
            "GRU": gru_grid,
        },
        "test": {
            "R3": r3,
            "SPARSE_ESN": esn,
            "GRU": gru,
        },
        "paired_r3_vs_sparse_esn": r3_vs_esn,
        "paired_r3_vs_gru": r3_vs_gru,
        "r3_sparse_runtime_ratio_vs_esn": runtime_ratio,
        "preregistered_gate_components": {
            "r3_beats_sparse_esn_4_of_5": r3_vs_esn["a_wins"] >= 4,
            "r3_not_more_than_2x_sparse_esn_state_update": (
                runtime_ratio is not None and runtime_ratio <= 2.0
            ),
            "r3_relative_nmse_improvement_over_sparse_esn": (
                -r3_vs_esn["relative_nmse_change_a_vs_b"]
                if r3_vs_esn["relative_nmse_change_a_vs_b"] is not None
                else None
            ),
        },
        "private_panam_data_used": False,
        "production_readiness_claimed": False,
        "promotion_decision": "NOT_MADE_BY_SINGLE_TASK",
        "limitations": [
            "single MaleCNS connectome and one 192-node weighted-degree subgraph",
            "generalized NARMA task is synthetic and not PANAM telemetry",
            "bounded hyperparameter grids",
            "GRU compute path is PyTorch CPU while reservoirs use SciPy sparse CPU",
            "runtime measurements are GitHub-hosted CI observations and are not portable production benchmarks",
            "model bytes are in-memory parameter/storage estimates rather than deployment package sizes",
        ],
    }

    print(json.dumps(output, sort_keys=True, allow_nan=False))
    print(f"PANAM_PUBLIC_FLYCORE_STRONG_BASELINE_NARMA{args.order}=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""PANAM Frozen Reservoir Adaptation V1.

Neutral practical benchmark derived from FlyCore low-data evidence.

Task switch directions:
- NARMA10 -> NARMA20
- NARMA20 -> NARMA10

Models:
- ER_ESN: uniform random sparse reservoir
- MODULAR_ESN: 4-module sparse reservoir, 80% intra-module edges
- SMALL_WORLD_ESN: directed local ring-neighborhood + random shortcuts
- R3_MALECNS: biological MaleCNS weight-placement control
- GRU: source-pretrained learned recurrent reference, then target fine-tuning

Reservoir recurrent cores remain frozen during target adaptation; only a ridge
readout is fit. GRU fine-tunes all recurrent parameters on the same number of
target labels.

All data are deterministic synthetic NARMA. No private PANAM data are used.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "flycore"))
import run_strong_baseline_narma as strong

NODE_COUNT = 192
EDGE_COUNT = 3377
BUDGETS = (10, 25, 50, 100)
TEST_SEEDS = (701, 709, 719, 727, 733)
RIDGE = 1e-3

SOURCE_CONFIGS = {
    10: {
        "R3_MALECNS": {"gain": 1.15, "input_scale": 0.55, "leak": 0.50},
        "NEUTRAL": {"gain": 1.15, "input_scale": 0.80, "leak": 0.30},
        "GRU": {"hidden_units": 64, "learning_rate": 0.003, "epochs": 59},
    },
    20: {
        "R3_MALECNS": {"gain": 1.15, "input_scale": 0.80, "leak": 0.30},
        "NEUTRAL": {"gain": 1.15, "input_scale": 0.80, "leak": 0.15},
        "GRU": {"hidden_units": 64, "learning_rate": 0.003, "epochs": 49},
    },
}

GRU_FINETUNE_LR = 0.001
GRU_FINETUNE_EPOCHS = 25


def scale_abs_row_sum(W: sp.csr_matrix, target: float) -> sp.csr_matrix:
    row = np.asarray(np.abs(W).sum(axis=1)).ravel()
    mx = float(np.max(row))
    if mx <= 0:
        raise RuntimeError("zero_recurrent_matrix")
    return (W * (target / mx)).tocsr()


def random_signed_weights(rng: np.random.Generator, count: int) -> np.ndarray:
    w = rng.normal(0.0, 1.0, size=count)
    tiny = np.abs(w) < 1e-8
    if np.any(tiny):
        w[tiny] = 1.0
    return w.astype(np.float64)


def build_er(seed: int, gain: float) -> sp.csr_matrix:
    rng = np.random.default_rng(seed + 31_001)
    codes = rng.choice(NODE_COUNT * NODE_COUNT, size=EDGE_COUNT, replace=False)
    pre = codes // NODE_COUNT
    post = codes % NODE_COUNT
    data = random_signed_weights(rng, EDGE_COUNT)
    W = sp.csr_matrix(
        (data, (post, pre)),
        shape=(NODE_COUNT, NODE_COUNT),
        dtype=np.float64,
    )
    W.sum_duplicates()
    return scale_abs_row_sum(W, gain)


def build_modular(seed: int, gain: float) -> sp.csr_matrix:
    rng = np.random.default_rng(seed + 32_003)
    all_codes = np.arange(NODE_COUNT * NODE_COUNT, dtype=np.int64)
    pre = all_codes // NODE_COUNT
    post = all_codes % NODE_COUNT

    module_size = NODE_COUNT // 4
    pre_mod = pre // module_size
    post_mod = post // module_size
    intra_codes = all_codes[pre_mod == post_mod]
    inter_codes = all_codes[pre_mod != post_mod]

    intra_count = int(round(EDGE_COUNT * 0.80))
    inter_count = EDGE_COUNT - intra_count
    chosen = np.concatenate(
        [
            rng.choice(intra_codes, size=intra_count, replace=False),
            rng.choice(inter_codes, size=inter_count, replace=False),
        ]
    )
    rng.shuffle(chosen)

    cpre = chosen // NODE_COUNT
    cpost = chosen % NODE_COUNT
    data = random_signed_weights(rng, EDGE_COUNT)
    W = sp.csr_matrix(
        (data, (cpost, cpre)),
        shape=(NODE_COUNT, NODE_COUNT),
        dtype=np.float64,
    )
    W.sum_duplicates()
    return scale_abs_row_sum(W, gain)


def build_small_world(seed: int, gain: float) -> sp.csr_matrix:
    rng = np.random.default_rng(seed + 33_007)
    edges: set[tuple[int, int]] = set()

    # Directed ring-neighborhood backbone: +/- 8 positions => 3,072 edges.
    radius = 8
    for pre in range(NODE_COUNT):
        for d in range(1, radius + 1):
            edges.add((pre, (pre + d) % NODE_COUNT))
            edges.add((pre, (pre - d) % NODE_COUNT))

    if len(edges) > EDGE_COUNT:
        raise RuntimeError("small_world_backbone_exceeds_edge_budget")

    while len(edges) < EDGE_COUNT:
        pre = int(rng.integers(0, NODE_COUNT))
        post = int(rng.integers(0, NODE_COUNT))
        edges.add((pre, post))

    ordered = sorted(edges)
    pre = np.fromiter((x[0] for x in ordered), dtype=np.int64)
    post = np.fromiter((x[1] for x in ordered), dtype=np.int64)
    data = random_signed_weights(rng, len(ordered))
    W = sp.csr_matrix(
        (data, (post, pre)),
        shape=(NODE_COUNT, NODE_COUNT),
        dtype=np.float64,
    )
    W.sum_duplicates()
    return scale_abs_row_sum(W, gain)


def build_r3(pre, post, weights, gain: float) -> sp.csr_matrix:
    data = np.log1p(weights.astype(np.float64))
    W = sp.csr_matrix(
        (data, (post, pre)),
        shape=(NODE_COUNT, NODE_COUNT),
        dtype=np.float64,
    )
    W.sum_duplicates()
    return scale_abs_row_sum(W, gain)


def drive(W: sp.csr_matrix, u: np.ndarray, win: np.ndarray, leak: float):
    x = np.zeros(W.shape[0], dtype=np.float64)
    states = np.empty((u.size, W.shape[0]), dtype=np.float64)
    start = time.perf_counter()
    for t, val in enumerate(u):
        x = (1.0 - leak) * x + leak * np.tanh(W.dot(x) + win * val)
        states[t] = x
    elapsed = time.perf_counter() - start
    return states, elapsed


def fit_ridge(states, target, start: int, end: int):
    X = states[start:end]
    X = np.column_stack([np.ones(X.shape[0]), X])
    Y = target[start:end]
    reg = np.eye(X.shape[1], dtype=np.float64) * RIDGE
    reg[0, 0] = 0.0

    t0 = time.perf_counter()
    coef = np.linalg.solve(X.T @ X + reg, X.T @ Y)
    elapsed = time.perf_counter() - t0
    return coef, elapsed


def predict_ridge(coef, states, start: int, end: int):
    X = states[start:end]
    X = np.column_stack([np.ones(X.shape[0]), X])
    return X @ coef


def sparse_model_bytes(W: sp.csr_matrix, win: np.ndarray, coef: np.ndarray) -> int:
    return int(
        W.data.nbytes
        + W.indices.nbytes
        + W.indptr.nbytes
        + win.nbytes
        + coef.nbytes
    )


def target_reservoir_runs(
    family: str,
    source_order: int,
    target_order: int,
    seed: int,
    pre,
    post,
    contact_weight,
):
    cfg_key = "R3_MALECNS" if family == "R3_MALECNS" else "NEUTRAL"
    cfg = SOURCE_CONFIGS[source_order][cfg_key]

    if family == "R3_MALECNS":
        W = build_r3(pre, post, contact_weight, cfg["gain"])
    elif family == "ER_ESN":
        W = build_er(seed, cfg["gain"])
    elif family == "MODULAR_ESN":
        W = build_modular(seed, cfg["gain"])
    elif family == "SMALL_WORLD_ESN":
        W = build_small_world(seed, cfg["gain"])
    else:
        raise ValueError(family)

    u, target, data_seed = strong.generate_narma(
        target_order, seed, strong.TEST_STEPS, return_data_seed=True
    )

    rng = np.random.default_rng(seed + 17_003)
    win = (
        rng.normal(0.0, 1.0, size=NODE_COUNT).astype(np.float64)
        * cfg["input_scale"]
    )

    states, state_seconds = drive(W, u, win, cfg["leak"])
    test_start = strong.WASHOUT + strong.TRAIN_STEPS
    test_end = test_start + strong.TEST_STEPS

    runs = []
    for budget in BUDGETS:
        train_start = strong.WASHOUT
        train_end = train_start + budget
        coef, train_seconds = fit_ridge(
            states, target, train_start, train_end
        )
        pred = predict_ridge(coef, states, test_start, test_end)
        runs.append(
            {
                "requested_seed": int(seed),
                "data_seed": int(data_seed),
                "budget": int(budget),
                "nmse": strong.nmse(
                    target[test_start:test_end], pred
                ),
                "adapt_train_seconds": float(train_seconds),
                "state_update_microseconds_per_step": float(
                    state_seconds / u.size * 1e6
                ),
                "model_bytes": sparse_model_bytes(W, win, coef),
                "recurrent_nonzeros": int(W.nnz),
            }
        )
    return runs


def task_input_max(order: int) -> float:
    return 0.5 if order == 10 else 0.2


def prepare_windows(u, target, start, end, order):
    X, Y = strong.make_windows(u, target, start, end)
    mx = task_input_max(order)
    X = ((X - mx / 2.0) / (mx / 2.0))[:, :, None]
    return X.astype(np.float32), Y.astype(np.float32)


def pretrain_source_gru(source_order: int, seed: int):
    torch = strong._torch()
    cfg = SOURCE_CONFIGS[source_order]["GRU"]
    torch.manual_seed(seed + 71_003)

    u, target, data_seed = strong.generate_narma(
        source_order, seed, strong.TEST_STEPS, return_data_seed=True
    )
    start = strong.WASHOUT
    end = start + strong.TRAIN_STEPS
    X, Y = prepare_windows(u, target, start, end, source_order)

    y_mean = float(np.mean(Y))
    y_std = float(np.std(Y))
    if not np.isfinite(y_std) or y_std <= 0:
        raise RuntimeError("invalid_source_target_std")
    Yn = (Y - y_mean) / y_std

    tx = torch.from_numpy(X)
    ty = torch.from_numpy(Yn)
    model = strong.GRUNetFactory.make(cfg["hidden_units"])
    opt = torch.optim.Adam(model.parameters(), lr=cfg["learning_rate"])
    loss_fn = torch.nn.MSELoss()
    generator = torch.Generator().manual_seed(seed + 72_003)

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
    elapsed = time.perf_counter() - t0

    return {
        "state_dict": copy.deepcopy(model.state_dict()),
        "source_data_seed": int(data_seed),
        "source_train_seconds": float(elapsed),
    }


def adapt_gru(
    source_order: int,
    target_order: int,
    seed: int,
    budget: int,
    source_state,
):
    torch = strong._torch()
    torch.manual_seed(seed + 81_003)

    u, target, data_seed = strong.generate_narma(
        target_order, seed, strong.TEST_STEPS, return_data_seed=True
    )
    train_start = strong.WASHOUT
    train_end = train_start + budget
    test_start = strong.WASHOUT + strong.TRAIN_STEPS
    test_end = test_start + strong.TEST_STEPS

    Xtr, Ytr = prepare_windows(
        u, target, train_start, train_end, target_order
    )
    Xte, Yte = prepare_windows(
        u, target, test_start, test_end, target_order
    )

    y_mean = float(np.mean(Ytr))
    y_std = float(np.std(Ytr))
    if not np.isfinite(y_std) or y_std <= 0:
        raise RuntimeError("invalid_target_adaptation_std")

    Ytrn = (Ytr - y_mean) / y_std
    tx = torch.from_numpy(Xtr)
    ty = torch.from_numpy(Ytrn)
    vx = torch.from_numpy(Xte)

    model = strong.GRUNetFactory.make(
        SOURCE_CONFIGS[source_order]["GRU"]["hidden_units"]
    )
    model.load_state_dict(copy.deepcopy(source_state))
    opt = torch.optim.Adam(model.parameters(), lr=GRU_FINETUNE_LR)
    loss_fn = torch.nn.MSELoss()
    generator = torch.Generator().manual_seed(seed + 82_003 + budget)

    t0 = time.perf_counter()
    for _epoch in range(GRU_FINETUNE_EPOCHS):
        model.train()
        perm = torch.randperm(tx.shape[0], generator=generator)
        for begin in range(0, tx.shape[0], max(1, min(strong.GRU_BATCH, tx.shape[0]))):
            idx = perm[begin:begin + strong.GRU_BATCH]
            opt.zero_grad(set_to_none=True)
            pred = model(tx[idx])
            loss = loss_fn(pred, ty[idx])
            loss.backward()
            opt.step()
    adapt_seconds = time.perf_counter() - t0

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
        "adapt_train_seconds": float(adapt_seconds),
        "inference_microseconds_per_window": float(
            infer_seconds / Xte.shape[0] * 1e6
        ),
        "parameter_count": params,
        "model_bytes": model_bytes,
    }


def aggregate(runs, budget):
    xs = [x for x in runs if x["budget"] == budget]
    return {
        "mean_nmse": float(np.mean([x["nmse"] for x in xs])),
        "median_nmse": float(np.median([x["nmse"] for x in xs])),
        "mean_adapt_train_seconds": float(
            np.mean([x["adapt_train_seconds"] for x in xs])
        ),
        "seed_nmse": {
            str(x["requested_seed"]): float(x["nmse"]) for x in xs
        },
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source-order", type=int, choices=(10, 20), required=True)
    p.add_argument("--graph", required=True, type=strong.base.Path)
    p.add_argument("--annotations", required=True, type=strong.base.Path)
    args = p.parse_args()

    source_order = args.source_order
    target_order = 20 if source_order == 10 else 10

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
    strong.base.NODE_COUNT = NODE_COUNT
    try:
        selected, traced_rows = strong.base.select_top_degree_traced(
            args.graph, traced
        )
    finally:
        strong.base.NODE_COUNT = old
    pre, post, contact_weight = strong.base.extract_subgraph(
        args.graph, selected
    )
    if len(pre) != EDGE_COUNT:
        raise RuntimeError(f"unexpected_r3_edge_count:{len(pre)}")

    families = (
        "ER_ESN",
        "MODULAR_ESN",
        "SMALL_WORLD_ESN",
        "R3_MALECNS",
    )
    runs = {family: [] for family in families}
    runs["GRU"] = []
    source_gru = {}

    for seed in TEST_SEEDS:
        source_gru[seed] = pretrain_source_gru(source_order, seed)

        for family in families:
            runs[family].extend(
                target_reservoir_runs(
                    family,
                    source_order,
                    target_order,
                    seed,
                    pre,
                    post,
                    contact_weight,
                )
            )

        for budget in BUDGETS:
            runs["GRU"].append(
                adapt_gru(
                    source_order,
                    target_order,
                    seed,
                    budget,
                    source_gru[seed]["state_dict"],
                )
            )

    agg = {
        family: {
            str(b): aggregate(family_runs, b)
            for b in BUDGETS
        }
        for family, family_runs in runs.items()
    }

    neutral = ("ER_ESN", "MODULAR_ESN", "SMALL_WORLD_ESN")
    per_budget = {}
    family_gate_counts = {family: 0 for family in neutral}
    biological_specificity_count = 0

    for b in BUDGETS:
        key = str(b)
        gru_nmse = agg["GRU"][key]["mean_nmse"]
        gru_time = agg["GRU"][key]["mean_adapt_train_seconds"]

        best_neutral = min(
            neutral,
            key=lambda f: agg[f][key]["mean_nmse"],
        )
        best_neutral_nmse = agg[best_neutral][key]["mean_nmse"]

        family_pass = {}
        for family in neutral:
            q = agg[family][key]["mean_nmse"] <= 1.10 * gru_nmse
            t = (
                agg[family][key]["mean_adapt_train_seconds"]
                <= gru_time / 100.0
                if gru_time > 0
                else False
            )
            passed = bool(q and t)
            family_pass[family] = {
                "quality_within_10pct_of_GRU": bool(q),
                "at_least_100x_faster_adaptation": bool(t),
                "budget_gate": passed,
            }
            if passed:
                family_gate_counts[family] += 1

        r3_nmse = agg["R3_MALECNS"][key]["mean_nmse"]
        r3_specific = (
            best_neutral_nmse > 0
            and (best_neutral_nmse - r3_nmse) / best_neutral_nmse >= 0.05
        )
        if r3_specific:
            biological_specificity_count += 1

        per_budget[key] = {
            "best_neutral_family": best_neutral,
            "best_neutral_mean_nmse": float(best_neutral_nmse),
            "R3_mean_nmse": float(r3_nmse),
            "GRU_mean_nmse": float(gru_nmse),
            "family_gates": family_pass,
            "R3_beats_best_neutral_by_at_least_5pct": bool(r3_specific),
        }

    output = {
        "schema": "panam.public.frozen_reservoir.task_switch_adaptation.v1",
        "scope": "PUBLIC_SYNTHETIC_NEUTRAL_RESERVOIR_ADAPTATION_NOT_PRODUCTION",
        "source_task": f"NARMA{source_order}",
        "target_task": f"NARMA{target_order}",
        "target_budgets": list(BUDGETS),
        "test_seeds": list(TEST_SEEDS),
        "selected_nodes": int(selected.size),
        "selected_edges": int(len(pre)),
        "selected_body_id_sha256": strong.base.hashlib.sha256(
            selected.tobytes()
        ).hexdigest(),
        "configs": {
            "source": SOURCE_CONFIGS[source_order],
            "GRU_target_finetune_learning_rate": GRU_FINETUNE_LR,
            "GRU_target_finetune_epochs": GRU_FINETUNE_EPOCHS,
            "ridge": RIDGE,
        },
        "fairness": {
            "same_target_label_budget": True,
            "same_target_series_within_seed": True,
            "same_target_test_tail_within_seed": True,
            "reservoir_recurrent_cores_frozen": True,
            "GRU_source_pretrained_and_target_finetuned": True,
            "no_target_test_hyperparameter_tuning": True,
        },
        "aggregate": agg,
        "per_budget_decision": per_budget,
        "direction_decision": {
            "neutral_family_budget_gate_counts": family_gate_counts,
            "neutral_direction_gate_passed": any(
                count >= 3 for count in family_gate_counts.values()
            ),
            "R3_biological_specificity_budget_count": biological_specificity_count,
            "R3_biological_specificity_direction_gate_passed": (
                biological_specificity_count >= 3
            ),
        },
        "source_gru_pretrain_seconds": {
            str(seed): source_gru[seed]["source_train_seconds"]
            for seed in TEST_SEEDS
        },
        "runs": runs,
        "private_panam_data_used": False,
        "production_readiness_claimed": False,
        "promotion_decision": "NOT_MADE_BY_SINGLE_DIRECTION",
        "limitations": [
            "synthetic NARMA task switch only",
            "one 192-node MaleCNS subgraph for R3",
            "neutral reservoirs inherit the source-task ER operating point rather than per-topology retuning",
            "GRU target fine-tuning uses a fixed preregistered learning rate and epoch count",
            "reservoirs do not learn from the source task except through their frozen operating point, while GRU source weights are pretrained",
            "CPU CI timing is descriptive and not a deployment benchmark",
        ],
    }

    print(json.dumps(output, sort_keys=True, allow_nan=False))
    print(
        f"PANAM_PUBLIC_FROZEN_RESERVOIR_SWITCH_{source_order}_TO_{target_order}=PASS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

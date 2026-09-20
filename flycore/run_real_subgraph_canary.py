#!/usr/bin/env python3
"""Bounded public canary on a real MaleCNS v1.0 traced-neuron subgraph.

This is a research pipeline canary, not a production-readiness test and not a
claim that Drosophila topology is useful for PANAM. It compares R0-R3 under one
frozen synthetic temporal-classification contract using a deterministic
task-independent subgraph selected only by weighted graph degree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.feather as feather
import pyarrow.ipc as ipc

GRAPH_NAME = "connectome-weights-male-cns-v1.0-minconf-0.5.feather"
GRAPH_BYTES = 1_051_241_946
GRAPH_SHA256 = "e35da783d1c686b2b58b3b87cd6a403ae43bfcfba8bff28e08ef752c1a56afc1"
ANNOTATION_NAME = "body-annotations-male-cns-v1.0-minconf-0.5.feather"
ANNOTATION_BYTES = 14_483_314
ANNOTATION_SHA256 = "2177e246113e4cfbf1e7772ec37c6da1955ff22e8063d0b1f833101f99a9a3b2"
TRACED_COUNT = 165_122

NODE_COUNT = 96
SEEDS = (11, 29, 47)
EVENT_DIM = 6
LEAK = 0.45
RECURRENT_ROW_SUM = 0.70
RIDGE = 1e-3

MOTIFS = (
    (0, 1, 5, 0, 1, 0),
    (2, 5, 1, 2, 5, 2),
    (3, 1, 5, 3, 1, 3),
    (4, 5, 0, 4, 5, 4),
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require_artifact(path: Path, name: str, size: int, digest: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"{name}:not_regular_file")
    if path.name != name:
        raise RuntimeError(f"{name}:filename_mismatch")
    if path.stat().st_size != size:
        raise RuntimeError(f"{name}:size_mismatch")
    if sha256_file(path) != digest:
        raise RuntimeError(f"{name}:sha256_mismatch")


def read_traced_ids(annotation_path: Path) -> np.ndarray:
    table = feather.read_table(
        annotation_path,
        columns=["bodyId", "status"],
        memory_map=True,
    )
    body = table["bodyId"].to_numpy(zero_copy_only=False).astype(np.int64, copy=False)
    status = np.array(table["status"].to_pylist(), dtype=object)
    traced = np.sort(body[status == "Traced"])
    if traced.size != TRACED_COUNT:
        raise RuntimeError(f"traced_count_mismatch:{traced.size}")
    if np.unique(traced).size != traced.size:
        raise RuntimeError("traced_body_ids_not_unique")
    return traced


def lookup_sorted(sorted_ids: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    idx = np.searchsorted(sorted_ids, values)
    safe = np.minimum(idx, sorted_ids.size - 1)
    valid = (idx < sorted_ids.size) & (sorted_ids[safe] == values)
    return idx, valid


def iter_graph_batches(graph_path: Path):
    mm = pa.memory_map(str(graph_path), "r")
    reader = ipc.open_file(mm)
    names = tuple(reader.schema.names)
    if names != ("body_pre", "body_post", "weight"):
        raise RuntimeError(f"graph_schema_mismatch:{names}")
    for i in range(reader.num_record_batches):
        batch = reader.get_batch(i)
        yield (
            batch.column(0).to_numpy(zero_copy_only=False).astype(np.int64, copy=False),
            batch.column(1).to_numpy(zero_copy_only=False).astype(np.int64, copy=False),
            batch.column(2).to_numpy(zero_copy_only=False).astype(np.int64, copy=False),
        )


def select_top_degree_traced(graph_path: Path, traced: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    degree = np.zeros(traced.size, dtype=np.float64)
    traced_edge_rows = 0

    for pre, post, weight in iter_graph_batches(graph_path):
        pi, pv = lookup_sorted(traced, pre)
        qi, qv = lookup_sorted(traced, post)
        mask = pv & qv
        if not np.any(mask):
            continue
        w = weight[mask].astype(np.float64, copy=False)
        np.add.at(degree, pi[mask], w)
        np.add.at(degree, qi[mask], w)
        traced_edge_rows += int(mask.sum())

    if np.count_nonzero(degree) < NODE_COUNT:
        raise RuntimeError("insufficient_traced_nodes_with_degree")

    order = np.lexsort((traced, -degree))
    selected_idx = order[:NODE_COUNT]
    selected_ids = np.sort(traced[selected_idx])
    return selected_ids, np.array([traced_edge_rows], dtype=np.int64)


def extract_subgraph(graph_path: Path, selected_ids: np.ndarray):
    codes = []
    weights = []
    n = selected_ids.size

    for pre, post, weight in iter_graph_batches(graph_path):
        pi, pv = lookup_sorted(selected_ids, pre)
        qi, qv = lookup_sorted(selected_ids, post)
        mask = pv & qv
        if not np.any(mask):
            continue
        codes.append(pi[mask].astype(np.int64) * n + qi[mask].astype(np.int64))
        weights.append(weight[mask].astype(np.float64))

    if not codes:
        raise RuntimeError("selected_subgraph_has_no_edges")

    code = np.concatenate(codes)
    w = np.concatenate(weights)
    unique, inverse = np.unique(code, return_inverse=True)
    agg = np.zeros(unique.size, dtype=np.float64)
    np.add.at(agg, inverse, w)

    pre = unique // n
    post = unique % n
    if unique.size < n:
        raise RuntimeError(f"selected_subgraph_too_sparse:{unique.size}")
    return pre, post, agg


def rewire_degree_preserving(pre: np.ndarray, post: np.ndarray, seed: int):
    rng = np.random.default_rng(seed)
    edges = [(int(a), int(b)) for a, b in zip(pre, post)]
    occupied = set(edges)
    m = len(edges)
    attempts = min(100_000, max(10_000, m * 8))
    swaps = 0

    for _ in range(attempts):
        i, j = rng.integers(0, m, size=2)
        if i == j:
            continue
        a, b = edges[int(i)]
        c, d = edges[int(j)]
        n1 = (a, d)
        n2 = (c, b)
        if n1 == n2:
            continue
        old1, old2 = edges[int(i)], edges[int(j)]
        if n1 not in (old1, old2) and n1 in occupied:
            continue
        if n2 not in (old1, old2) and n2 in occupied:
            continue
        occupied.discard(old1)
        occupied.discard(old2)
        occupied.add(n1)
        occupied.add(n2)
        edges[int(i)] = n1
        edges[int(j)] = n2
        swaps += 1

    if swaps < max(100, m // 10):
        raise RuntimeError(f"insufficient_degree_preserving_swaps:{swaps}")

    rp = np.fromiter((a for a, _ in edges), dtype=np.int64, count=m)
    rq = np.fromiter((b for _, b in edges), dtype=np.int64, count=m)
    return rp, rq, swaps


def build_matrix(
    variant: str,
    pre: np.ndarray,
    post: np.ndarray,
    contact_weight: np.ndarray,
    n: int,
    seed: int,
):
    rng = np.random.default_rng(seed)
    m = pre.size
    base = np.log1p(contact_weight.astype(np.float64))

    if variant == "R0":
        if m > n * n:
            raise RuntimeError("edge_count_exceeds_dense_pair_space")
        codes = rng.choice(n * n, size=m, replace=False)
        vp = codes // n
        vq = codes % n
        vw = rng.permutation(base)
        swaps = None
    elif variant == "R1":
        vp, vq, swaps = rewire_degree_preserving(pre, post, seed + 7001)
        vw = rng.permutation(base)
    elif variant == "R2":
        vp, vq = pre, post
        vw = rng.permutation(base)
        swaps = None
    elif variant == "R3":
        vp, vq = pre, post
        vw = base.copy()
        swaps = None
    else:
        raise ValueError(variant)

    W = np.zeros((n, n), dtype=np.float32)
    np.add.at(W, (vq, vp), vw.astype(np.float32))
    row_sum = np.abs(W).sum(axis=1)
    max_row = float(row_sum.max())
    if max_row <= 0:
        raise RuntimeError("zero_recurrent_matrix")
    W *= np.float32(RECURRENT_ROW_SUM / max_row)
    return W, swaps


def make_dataset(seed: int, per_class: int, prefix_len: int):
    rng = np.random.default_rng(seed)
    seqs = []
    labels = []
    for label, motif in enumerate(MOTIFS):
        for _ in range(per_class):
            prefix = rng.integers(0, EVENT_DIM, size=prefix_len, dtype=np.int64)
            # Non-label-specific prefix perturbation prevents a trivial fixed prefix.
            if rng.random() < 0.35:
                prefix[int(rng.integers(0, prefix_len))] = int(rng.integers(0, EVENT_DIM))
            seq = np.concatenate([prefix, np.array(motif, dtype=np.int64)])
            seqs.append(seq)
            labels.append(label)
    order = rng.permutation(len(seqs))
    return np.stack(seqs)[order], np.array(labels, dtype=np.int64)[order]


def reservoir_features(seqs: np.ndarray, W: np.ndarray, Win: np.ndarray):
    samples, steps = seqs.shape
    n = W.shape[0]
    state = np.zeros((samples, n), dtype=np.float32)
    eye = np.eye(EVENT_DIM, dtype=np.float32)

    for t in range(steps):
        u = eye[seqs[:, t]]
        drive = state @ W.T + u @ Win.T
        state = (1.0 - LEAK) * state + LEAK * np.tanh(drive)
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


def evaluate_variant(variant, pre, post, weights, n, seed):
    W, swaps = build_matrix(variant, pre, post, weights, n, seed)
    rng = np.random.default_rng(seed + 101)
    Win = rng.normal(0.0, 0.55, size=(n, EVENT_DIM)).astype(np.float32)

    train_seq, train_y = make_dataset(seed + 201, per_class=40, prefix_len=12)
    test_seq, test_y = make_dataset(seed + 1201, per_class=20, prefix_len=12)

    train_x = reservoir_features(train_seq, W, Win)
    test_x = reservoir_features(test_seq, W, Win)
    readout = ridge_readout(train_x, train_y, classes=len(MOTIFS))
    pred = predict(readout, test_x)

    return {
        "accuracy": float(np.mean(pred == test_y)),
        "macro_f1": macro_f1(test_y, pred, len(MOTIFS)),
        "degree_preserving_swaps": swaps,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--graph", required=True, type=Path)
    p.add_argument("--annotations", required=True, type=Path)
    args = p.parse_args()

    require_artifact(args.graph, GRAPH_NAME, GRAPH_BYTES, GRAPH_SHA256)
    require_artifact(args.annotations, ANNOTATION_NAME, ANNOTATION_BYTES, ANNOTATION_SHA256)

    traced = read_traced_ids(args.annotations)
    selected, traced_rows = select_top_degree_traced(args.graph, traced)
    pre, post, weights = extract_subgraph(args.graph, selected)

    result = {
        "schema": "panam.public.flycore.real_subgraph_canary.v1",
        "scope": "BOUNDED_REAL_CONNECTOME_CANARY_NOT_PRODUCTION",
        "scientific_result": False,
        "dataset": "MaleCNS v1.0",
        "selection_rule": "top weighted-degree neurons among status=Traced; task-independent",
        "traced_neuron_count": int(traced.size),
        "traced_to_traced_edge_rows": int(traced_rows[0]),
        "selected_nodes": int(selected.size),
        "selected_edges": int(pre.size),
        "selected_contact_weight_sum": float(weights.sum()),
        "selected_body_id_sha256": hashlib.sha256(selected.tobytes()).hexdigest(),
        "task": {
            "name": "synthetic_temporal_event_route_classification",
            "classes": len(MOTIFS),
            "event_dim": EVENT_DIM,
            "train_sequences_per_class": 40,
            "test_sequences_per_class": 20,
            "prefix_length": 12,
            "motif_length": len(MOTIFS[0]),
        },
        "seeds": list(SEEDS),
        "variants": {},
        "private_panam_data_used": False,
        "credentials_used_for_dataset": False,
        "autonomous_action": False,
        "promotion_decision": "NOT_MADE_BY_CANARY",
    }

    for variant in ("R0", "R1", "R2", "R3"):
        runs = []
        for seed in SEEDS:
            runs.append(evaluate_variant(variant, pre, post, weights, selected.size, seed))
        result["variants"][variant] = {
            "runs": runs,
            "mean_accuracy": float(np.mean([x["accuracy"] for x in runs])),
            "mean_macro_f1": float(np.mean([x["macro_f1"] for x in runs])),
        }

    print(json.dumps(result, sort_keys=True))
    print("PANAM_PUBLIC_FLYCORE_REAL_SUBGRAPH_CANARY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Inspect official public MaleCNS v1.0 aggregate neurotransmitter predictions."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

EXPECTED_NAME = "body-neurotransmitters-male-cns-v1.0.feather"
MAX_BYTES = 80_000_000


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def compact_counts(values, limit=30):
    counts = Counter("<NULL>" if v is None else str(v) for v in values)
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return dict(items[:limit]), len(counts)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("artifact", type=Path)
    args = p.parse_args()
    path = args.artifact

    if not path.is_file() or path.is_symlink():
        raise SystemExit("artifact_must_be_regular_file")
    if path.name != EXPECTED_NAME:
        raise SystemExit("artifact_filename_mismatch")

    size = path.stat().st_size
    if size <= 0 or size > MAX_BYTES:
        raise SystemExit(f"artifact_size_out_of_bounds:{size}")

    import pyarrow as pa
    import pyarrow.feather as feather
    import pyarrow.ipc as ipc
    import pyarrow.types as pat

    mm = pa.memory_map(str(path), "r")
    reader = ipc.open_file(mm)
    schema = reader.schema
    rows = int(feather.read_table(path, columns=[], memory_map=True).num_rows)

    columns = [
        {"name": f.name, "type": str(f.type), "nullable": bool(f.nullable)}
        for f in schema
    ]

    table = feather.read_table(path, memory_map=True)
    categorical = {}
    numeric = {}
    for field in schema:
        col = table[field.name]
        if pat.is_string(field.type) or pat.is_dictionary(field.type):
            vals = col.to_pylist()
            counts, unique_count = compact_counts(vals)
            categorical[field.name] = {
                "unique_count": unique_count,
                "top_counts": counts,
            }
        elif pat.is_integer(field.type) or pat.is_floating(field.type):
            import pyarrow.compute as pc
            nonnull = int(col.length() - col.null_count)
            entry = {"nonnull": nonnull}
            if nonnull:
                mn = pc.min(col).as_py()
                mx = pc.max(col).as_py()
                entry["min"] = mn
                entry["max"] = mx
            numeric[field.name] = entry

    result = {
        "schema": "panam.public.flycore.malecns_neurotransmitters_metadata.v1",
        "artifact": path.name,
        "bytes": size,
        "sha256": sha256_file(path),
        "rows": rows,
        "record_batches": int(reader.num_record_batches),
        "arrow_columns": columns,
        "categorical_summary": categorical,
        "numeric_summary": numeric,
        "private_panam_data_used": False,
        "credentials_used": False,
    }

    print(json.dumps(result, sort_keys=True))
    print("PANAM_PUBLIC_FLYCORE_MALECNS_NEUROTRANSMITTERS_METADATA=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

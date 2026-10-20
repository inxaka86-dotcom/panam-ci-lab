#!/usr/bin/env python3
"""Inspect official public MaleCNS v1.0 neuron annotations."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

EXPECTED_NAME = "body-annotations-male-cns-v1.0-minconf-0.5.feather"
MAX_BYTES = 25_000_000


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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

    mm = pa.memory_map(str(path), "r")
    reader = ipc.open_file(mm)
    columns = [
        {"name": f.name, "type": str(f.type), "nullable": bool(f.nullable)}
        for f in reader.schema
    ]
    names = {c["name"] for c in columns}
    rows = int(feather.read_table(path, columns=[], memory_map=True).num_rows)

    result = {
        "schema": "panam.public.flycore.malecns_annotations_metadata.v1",
        "artifact": path.name,
        "bytes": size,
        "sha256": sha256_file(path),
        "rows": rows,
        "record_batches": int(reader.num_record_batches),
        "arrow_columns": columns,
        "credentials_used": False,
        "private_panam_data_used": False,
    }

    if "status" in names:
        values = feather.read_table(path, columns=["status"], memory_map=True)["status"].to_pylist()
        result["status_counts"] = {
            "<NULL>" if k is None else str(k): int(v)
            for k, v in sorted(Counter(values).items(), key=lambda kv: str(kv[0]))
        }

    if "superclass" in names:
        values = feather.read_table(path, columns=["superclass"], memory_map=True)["superclass"].to_pylist()
        result["superclass_nonempty"] = sum(
            1 for v in values if v is not None and str(v).strip()
        )

    if "bodyId" in names:
        body = feather.read_table(path, columns=["bodyId"], memory_map=True)["bodyId"]
        result["body_id_nonnull"] = int(body.length() - body.null_count)

    print(json.dumps(result, sort_keys=True))
    print("PANAM_PUBLIC_FLYCORE_MALECNS_ANNOTATIONS_METADATA=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

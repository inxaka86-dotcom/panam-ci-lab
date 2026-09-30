#!/usr/bin/env python3
"""Inspect the official public MaleCNS v1.0 connection graph.

Public-CI only. The script accepts one already-downloaded local file, computes
its exact SHA-256 and inspects Arrow/Feather metadata. It contains no PANAM
private paths, credentials, network clients or production identifiers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_NAME = "connectome-weights-male-cns-v1.0-minconf-0.5.feather"
MAX_BYTES = 1_300_000_000


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
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
    schema = reader.schema

    # Prefer metadata-only/zero-column row counting. Fall back to bounded
    # sequential batch metadata access if the installed Arrow build does not
    # preserve row count for an empty projection.
    row_count_method = "feather_zero_column_projection"
    try:
        zero = feather.read_table(path, columns=[], memory_map=True)
        rows = int(zero.num_rows)
    except Exception:
        rows = 0

    if rows <= 0:
        row_count_method = "ipc_record_batch_iteration"
        rows = 0
        for i in range(reader.num_record_batches):
            rows += int(reader.get_batch(i).num_rows)

    result = {
        "schema": "panam.public.flycore.malecns_metadata.v1",
        "dataset": "MaleCNS v1.0",
        "artifact": path.name,
        "bytes": size,
        "sha256": sha256_file(path),
        "arrow_columns": [
            {"name": field.name, "type": str(field.type), "nullable": field.nullable}
            for field in schema
        ],
        "record_batches": int(reader.num_record_batches),
        "rows": rows,
        "row_count_method": row_count_method,
        "source_url": (
            "https://storage.googleapis.com/flyem-male-cns/v1.0/"
            "connectome-data/flat-connectome/"
            "connectome-weights-male-cns-v1.0-minconf-0.5.feather"
        ),
        "private_panam_data_used": False,
        "credentials_used": False,
    }
    print(json.dumps(result, sort_keys=True))
    print("PANAM_PUBLIC_FLYCORE_MALECNS_METADATA=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

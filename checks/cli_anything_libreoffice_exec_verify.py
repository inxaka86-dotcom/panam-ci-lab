#!/usr/bin/env python3
"""Verify synthetic-only CLI-Anything LibreOffice executable pilot outputs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

MARKER = "PANAM_SYNTHETIC_EXEC_PILOT_V2"


def _inside(root: Path, path: Path) -> Path:
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise AssertionError(f"output escaped sandbox: {resolved}") from exc
    assert path.is_file(), path
    assert not path.is_symlink(), path
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sandbox", type=Path)
    args = parser.parse_args()

    root = args.sandbox.resolve(strict=True)
    assert root.is_dir()
    expected = {
        "project": root / "project.json",
        "odt": root / "pilot.odt",
        "pdf": root / "pilot.pdf",
        "docx": root / "pilot.docx",
    }
    for path in expected.values():
        _inside(root, path)

    project = json.loads(expected["project"].read_text(encoding="utf-8"))
    assert MARKER in json.dumps(project, ensure_ascii=False), "synthetic marker missing from project JSON"

    with ZipFile(expected["odt"]) as archive:
        names = archive.namelist()
        assert names and names[0] == "mimetype"
        info = archive.getinfo("mimetype")
        assert info.compress_type == ZIP_STORED
        assert archive.read("mimetype") == b"application/vnd.oasis.opendocument.text"
        content = archive.read("content.xml").decode("utf-8")
        assert MARKER in content
        assert "META-INF/manifest.xml" in names

    pdf = expected["pdf"].read_bytes()
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 500

    with ZipFile(expected["docx"]) as archive:
        names = set(archive.namelist())
        assert "[Content_Types].xml" in names
        assert "word/document.xml" in names
        assert not any(name.lower().endswith("vbaproject.bin") for name in names)
        document = archive.read("word/document.xml").decode("utf-8")
        assert MARKER in document

    report = {
        "schema": "panam.public-cli-anything-libreoffice-exec-evidence.v1",
        "synthetic_only": True,
        "authority": "public_research_evidence_only",
        "source_of_truth": False,
        "real_data_used": False,
        "network_during_execution": False,
        "overwrite_used": False,
        "import_used": False,
        "repl_used": False,
        "production_authority": False,
        "outputs": {name: {"sha256": _sha256(path), "bytes": path.stat().st_size} for name, path in expected.items()},
    }
    print(json.dumps(report, sort_keys=True, indent=2))
    print("PANAM_PUBLIC_CLI_ANYTHING_LIBREOFFICE_EXEC_V2=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

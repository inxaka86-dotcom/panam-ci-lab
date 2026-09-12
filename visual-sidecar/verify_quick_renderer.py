#!/usr/bin/env python3
"""Public-only synthetic qualification for an exact-pinned static renderer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

FORBIDDEN = (
    "<script",
    "javascript:",
    "<iframe",
    "<object",
    "<embed",
    "<form",
    "<input",
    "<button",
    " onload=",
    " onclick=",
    " onerror=",
)
EXTERNAL_REF_RE = re.compile(r"(?:href|src)=[\"']https?://", re.IGNORECASE)


def render(renderer: Path, spec: Path, output: Path, home: Path) -> str:
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(home),
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "",
    }
    completed = subprocess.run(
        ["node", str(renderer), str(spec), str(output)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        env=env,
    )
    if completed.returncode != 0:
        raise RuntimeError("renderer failed")
    return output.read_text(encoding="utf-8")


def assert_safe(html: str) -> None:
    lowered = html.lower()
    for marker in FORBIDDEN:
        assert marker not in lowered, marker
    assert not EXTERNAL_REF_RE.search(html), "external href/src present"
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html, "escaping proof missing"
    assert "presentation_only" in html, "authority marker missing"
    assert "Synthetic finding" in html, "synthetic finding missing"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("renderer", type=Path)
    parser.add_argument("spec", type=Path)
    args = parser.parse_args()
    renderer = args.renderer.resolve()
    spec = args.spec.resolve()
    assert renderer.is_file()
    assert spec.is_file()
    json.loads(spec.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory(prefix="public-visual-sidecar-") as tmp:
        work = Path(tmp)
        html_a = render(renderer, spec, work / "a.html", work)
        html_b = render(renderer, spec, work / "b.html", work)

    assert html_a == html_b, "renderer output is not deterministic"
    assert_safe(html_a)
    report = {
        "schema": "public.visual-sidecar-quick-qualification.v1",
        "synthetic_only": True,
        "private_repository_access": False,
        "production_data_used": False,
        "deterministic": True,
        "sha256": hashlib.sha256(html_a.encode("utf-8")).hexdigest(),
        "bytes": len(html_a.encode("utf-8")),
        "active_content_markers": 0,
        "external_http_refs": 0,
    }
    print(json.dumps(report, sort_keys=True, indent=2))
    print("PUBLIC_VISUAL_SIDECAR_QUICK_QUALIFICATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Prepare two equal-content, gold-free research workspaces. NO AGENT EXECUTION.

This is a synthetic *workspace exporter*, not a sandbox or model API client.
No model, network client, secrets, task answers, scorer or agent skills are
copied into either arm. The parent directory must be an approved disposable
workspace. All outputs are research data only; no production effect.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

from build_synthetic_targets import build

ARMS = ("base", "leanrea")
FILES = (
    "tasks.json",
    "targets/electron-app/package.json",
    "targets/electron-app/.webpack/main.js",
    "targets/electron-app/.vite/preload.js",
    "targets/libcapture_probe.so",
    "targets/libwire_probe.so",
    "targets/go_probe",
)
BANNED = frozenset(("SKILL.md", "score_synthetic.py", "AB_PLAN.md",
                   "test_score_synthetic.py", "expected_answers.json"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_inventory(root: Path) -> dict[str, str]:
    files = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Symlink in agent workspace")
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            if rel not in FILES:
                raise ValueError("Unexpected file in agent workspace")
            if stat.S_IMODE(path.stat().st_mode) != 0o600:
                raise ValueError("Agent workspace file must be nonexecutable 0600")
            files[rel] = sha256(path)
    if set(files) != set(FILES):
        raise ValueError("Incomplete agent workspace")
    return dict(sorted(files.items()))


def prepare(output: Path) -> dict:
    # Fail before creating anything if output is an existing directory, file or
    # dangling symlink. Only an existing, nonsymlinked disposable parent is allowed.
    if output.exists() or output.is_symlink():
        raise ValueError("Destination must be new and must not be a symlink")
    parent = output.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("Destination parent must be an existing real directory")
    with tempfile.TemporaryDirectory(prefix="leanrea-source-") as td:
        source = Path(td) / "source"
        source_manifest = build(source)
        if set(source_manifest["artifacts"]) != set(FILES):
            raise ValueError("Unexpected synthetic build outputs")
        # Create output only after synthetic build succeeded and inventory passed.
        output.mkdir(mode=0o700)
        inventories = {}
        for arm in ARMS:
            workspace = output / arm
            workspace.mkdir(mode=0o700)
            for rel in FILES:
                original = source / rel
                if original.is_symlink() or not original.is_file():
                    raise ValueError("Untrusted synthetic source")
                dest = workspace / rel
                dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                # Byte-for-byte copy, never hardlink/symlink to a shared source.
                shutil.copyfile(original, dest)
                dest.chmod(0o600)
            inventories[arm] = file_inventory(workspace)
        if inventories["base"] != inventories["leanrea"]:
            raise ValueError("Arm contents differ")
        tasks = json.loads((output / "base" / "tasks.json").read_text())
        if tasks.get("schema") != "panam.leanrea.synthetic-target-pack.v1":
            raise ValueError("Unexpected synthetic tasks")
        if any("answer" in json.dumps(c).lower() or "gold" in json.dumps(c).lower()
               for c in tasks["cases"]):
            raise ValueError("Task pack appears contaminated with labels")
        # Manifest is outside agent workspaces. No real route/performance evidence.
        report = {
            "schema": "panam.leanrea.equal-workspaces.v1",
            "mode": "OFFLINE_SYNTHETIC_NO_AGENT",
            "case_ids": source_manifest["case_ids"],
            "equal_byte_inventory": True,
            "gold_in_workspaces": False,
            "skill_in_workspaces": False,
            "network_sandbox_verified": False,
            "agent_execution": False,
            "source_hashes": inventories["base"],
        }
        manifest_path = output / "WORKSPACE_MANIFEST.json"
        manifest_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        manifest_path.chmod(0o600)
        if any((output / arm / name).exists() for arm in ARMS for name in BANNED):
            raise ValueError("Forbidden agent file included")
        return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    report = prepare(args.out)
    print(json.dumps(report, sort_keys=True))
    print("PANAM_LEANREA_EQUAL_WORKSPACES=PASS")


if __name__ == "__main__":
    main()
